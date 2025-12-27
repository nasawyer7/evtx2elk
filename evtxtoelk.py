import contextlib
import os
import mmap
import traceback
import json
import argparse
from collections import OrderedDict
from datetime import datetime
import sys
import xmltodict

from Evtx.Evtx import FileHeader
from Evtx.Views import evtx_file_xml_view
from elasticsearch import Elasticsearch, helpers


#stupid dumb patch
import Evtx.Nodes

# Save the original function
_original_get_variant_value = Evtx.Nodes.get_variant_value

def patched_get_variant_value(buf, offset, chunk, parent, type_, length=None):
    try:
        return _original_get_variant_value(buf, offset, chunk, parent, type_, length)
    except KeyError:
        if length is not None:
             return _original_get_variant_value(buf, offset, chunk, parent, 14, length)
        
        try:
             return _original_get_variant_value(buf, offset, chunk, parent, 8, length)
        except:
             return _original_get_variant_value(buf, offset, chunk, parent, 6, length)

Evtx.Nodes.get_variant_value = patched_get_variant_value
print("[*] Successfully monkey-patched Evtx to handle ALL unknown types (Universal Mode)")

class EvtxToElk:
    @staticmethod
    def bulk_to_elasticsearch(es, bulk_queue):
        try:
            helpers.bulk(es, bulk_queue)
            return True
        except helpers.BulkIndexError as e:
            print("\nFATAL ELASTICSEARCH ERROR:")
            if len(e.errors) > 0:
                print(json.dumps(e.errors[0], indent=2))
            else:
                print(e)
            return False
        except Exception as e:
            print(traceback.print_exc())
            return False

    @staticmethod
    def evtx_to_elk(filename, elk_ip, elk_index="hostlogs", bulk_queue_len_threshold=3000, metadata={}):
        bulk_queue = []
        es = Elasticsearch([elk_ip])

        try:
            settings_body = {
                "index.mapping.total_fields.limit": 5000
            }
            if not es.indices.exists(index=elk_index):
                es.indices.create(index=elk_index, body={"settings": settings_body})
            else:
                es.indices.put_settings(index=elk_index, body=settings_body)
        except Exception as e:
            pass

        with open(filename) as infile:
            with contextlib.closing(mmap.mmap(infile.fileno(), 0, access=mmap.ACCESS_READ)) as buf:
                fh = FileHeader(buf, 0x0)
                
                for xml, record in evtx_file_xml_view(fh):
                    try:
                        log_line = xmltodict.parse(xml)

                        try:
                            system_node = log_line.get("Event", {}).get("System", {})
                            event_id = system_node.get("EventID")
                            if isinstance(event_id, dict):
                                text_val = event_id.get("#text")
                                if text_val:
                                    log_line["Event"]["System"]["EventID"] = int(text_val)
                        except Exception:
                            pass

                        # Format the date field
                        try:
                            date_str = log_line.get("Event").get("System").get("TimeCreated").get("@SystemTime")
                            if date_str:
                                date = datetime.fromisoformat(date_str)
                                log_line['@timestamp'] = str(date.isoformat())
                                log_line["Event"]["System"]["TimeCreated"]["@SystemTime"] = str(date.isoformat())
                        except Exception:
                            pass

                        if log_line.get("Event") and log_line.get("Event").get("EventData"):
                            event_data_node = log_line.get("Event").get("EventData")
                            data_items = event_data_node.get("Data")

                            if isinstance(data_items, list):
                                clean_data = {}
                                for idx, item in enumerate(data_items):
                                    try:
                                        # Case A: Named Dictionary
                                        if isinstance(item, dict) and item.get("@Name"):
                                            key = str(item.get("@Name"))
                                            val = str(item.get("#text"))
                                            
                                            if key in ["NewTime", "PreviousTime", "OldTime"] and " " in val:
                                                val = val.replace(" ", "T")
                                            
                                            clean_data[key] = val

                                        # Case B: Unnamed Dictionary
                                        elif isinstance(item, dict):
                                            val = str(item.get("#text", ""))
                                            clean_data[f"Parameter_{idx}"] = val

                                        # Case C: Simple String
                                        elif isinstance(item, str):
                                            clean_data[f"Parameter_{idx}"] = item
                                    except:
                                        pass
                                
                                log_line["Event"]["EventData"]["Data"] = clean_data

                            elif isinstance(data_items, str):
                                log_line["Event"]["EventData"]["RawData"] = data_items
                                del log_line["Event"]["EventData"]["Data"]

                        # Insert data into queue
                        event_data = json.loads(json.dumps(log_line))
                        event_data["_index"] = elk_index
                        event_data["meta"] = metadata
                        bulk_queue.append(event_data)

                        if len(bulk_queue) == bulk_queue_len_threshold:
                            print(f'Bulking {len(bulk_queue)} records to ES...')
                            if EvtxToElk.bulk_to_elasticsearch(es, bulk_queue):
                                bulk_queue = []
                            else:
                                print('Failed to bulk data to Elasticsearch')
                                sys.exit(1)

                    except Exception as e:
                        pass

                # Flush remaining records
                if len(bulk_queue) > 0:
                    print(f'Bulking final {len(bulk_queue)} records to ES...')
                    if EvtxToElk.bulk_to_elasticsearch(es, bulk_queue):
                        bulk_queue = []
                    else:
                        print('Failed to bulk data to Elasticsearch')
                        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input_path', help="Evtx file or folder to parse") 
    parser.add_argument('elk_ip', default="localhost", help="IP (and port) of ELK instance")
    parser.add_argument('-i', default="hostlogs", help="ELK index to load data into")
    parser.add_argument('-s', default=3000, help="Size of queue")
    parser.add_argument('-meta', default={}, type=json.loads, help="Metadata to add to records")
    args = parser.parse_args()
    
    input_path = args.input_path
    if os.path.isdir(input_path):
        for filename in os.listdir(input_path):
            if filename.lower().endswith(".evtx"):
                file_path = os.path.join(input_path, filename)
                print(f"\n[+] Processing: {file_path}")
                try:
                    EvtxToElk.evtx_to_elk(file_path, args.elk_ip, elk_index=args.i, bulk_queue_len_threshold=int(args.s), metadata=args.meta)
                    print(f"[+] Finished: {file_path}")
                except Exception as e:
                    print(f"[!] FAILED to process {file_path}: {e}")
                    print(traceback.format_exc())
    elif os.path.isfile(input_path):
        print("processing one file")
        EvtxToElk.evtx_to_elk(input_path, args.elk_ip, elk_index=args.i, bulk_queue_len_threshold=int(args.s), metadata=args.meta)
        print("processing finished")
    else:
        print(f"Error: Path '{input_path}' is not a valid file or directory.")
        sys.exit(1)
