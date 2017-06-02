#Troubleshooting Production

##Tools
1. AWS Console Cloudwatch Dashboard - API-Write-Monitor-short2
    * this is the main tool.  It combines data from a lot of areas.
2. Scalyr Logs on endpoint boss.log and emperor.log
    * emperor.log is useful for seeing the actual requests.  Are people getting 200s, 400s or 500s?
    * It can be used to tell that someone is still uploading or have stopped. (if not using ingest.)
3. AWS Console EC2 Load Balancers - Monitor Tab
   * Can see number of 5XXs, 4XXs and 2XXs responses.  See unhealthy nodes 
4. AWS Console Lambda - 
   * click on multilambda - monitor tab
   * can get to lambda logs from here.
   * can see lambda throttling here.  I find it easier to see in Cloudwatch Dashboard
5. AWS Console StepFunctions -
       Can see if any state machines are failing
6. AWS Console DynamoDB - Tables - Select a Table - Metrics
   * from here you can see if a table is throttling, if it is hitting is write or read capacity

## Things to understand
* Lambda capacity is number of lambdas * average duration of lambda runtimes.
   * if lambdas have to start waiting on other things like DynamoDB tables or S3, then number of lambdas that can run 
   at a time decreases.
* Redis Max CPU is 3.0
* ingest-client does not use the Redis cache so using it will not effect Redis CPU 

## Scenarios


### Ingest is slow
* Current problems can arise from the DynamoDB. 
   * The TileIndex in DynamoDB could be hitting capacity.  Check in the
  the console and raise it if needed.
  * idIndex DynamoDB could be hitting capacity or more likely with our current solution hitting a hotspot.
     * To solve this problem we have temporarily disable idIndex from being used during writes.
  * Ingest does not currently handle time time-series data.  It can't get all the messages into the queue.  
  There is not a solution for this yet. We need to put more intellegence into the for loops so it doesn't try to load a
  single cube per message but set minimums
  * watch the upload and ingest queues.  
     * the upload queue should be staying at a steady rate.
     * **Dean** what were the things to look for if one side is getting larger than the other?
 
### Ingest stuck.  Upload SQS Queue is finished but the Ingest SQS Queue not moving.
* lambda will only pull a single message off of the ingest queue.  
  * It used to pull off two, but started crashing due to memory filling up.
  * If any lambdas fail now, there will be messages left in the ingest SQS Queue.
  * Solution: Dean created a tool, documented in his last day notes that can send lambdas at a specified rate to an SQS queue.
  
# Causes of problems
* **Redis hitting maximum CPU**.  This causes the endpoints to slow down.  It can cause more endpoints to be created without
actually helping elevate the problem.  Solution here is to have poeple start using the new no-cache option when querying.
* **Too much activity** can tip over the system and cause WRITE-LOCKs to occur.  
   * The first sign of this is that lambda during times is not staying 
constant, it means things could start getting bad.  Look for the bottleneck, is a dynamoDB table hitting 
capcity of throttling?  If we can not fix the problem, we need to lower the number concurrent nodes performers are using 
to write.  Some times we pause the performers for the system to catch up during heavy use.





  
