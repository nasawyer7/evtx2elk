EvtxtoElk
============

A lightweight tool to load Windows Event Log evtx files into Elasticsearch.

Examples
--------

Blog is initially avaliable here, it is slightly out of date but credit goes to the original authors: https://web.archive.org/web/20221209023101/https://www.dragos.com/blog/industry-news/evtxtoelk-a-python-module-to-load-windows-event-logs-into-elasticsearch/

I have now updated this script a bit. It now can parse folders or single files correctly. Also, now it will succeed in parsing timestamps from sysmon logs. Please let me know if there are any errors when using it. Email me at nathan@nathan2.com. 

Usage: 
python3 evtxtoelk.py ~/Downloads/ http://elastic:password@ip:9200  -i unit42

Downloads is the folder with evtx files to parse. You can also point at a single file. 
Change the password and ip to match your instance. 
i is the index. By default, it will upload to hostlogs if not specified.

Do not create the index first, this tool will do that. 

# Data view creation
Once the upload is finished, go to elk (kibana, port 5601) -> analytics -> discover.
In the top left, select the drop down to data views, and select create a data view. 

In the index pattern field, enter in the index that you specified with -i in the command. If you didn't specify an index, use hostlog. 
The name and timestamp field should autofill. Press save data view to kibana. 
