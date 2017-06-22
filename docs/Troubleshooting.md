#Troubleshooting Production

##Tools
1. AWS Console Cloudwatch Dashboard - API-Write-Monitor-short2
    * this is the main tool.  It combines data from a lot of areas.
2. Scalyr Logs
    * endpoint.production.boss emperor.log is useful for seeing the actual requests that are getting to the API servers.  Are people getting 200s, 400s or 500s? Also, it's useful to compare this to the ELB status page which can show you if the 500's are coming from the ELB or the API.
    	* It can be used to tell that someone is still uploading or have stopped. (if not using ingest.)
    * endpoint.production.boss boss.log is useful for seeing logging and errors in the API
    * activities.production.boss is useful for checking progress of ingest job creation and downsample processes

3. AWS Console EC2 Load Balancers - Monitor Tab
   * Can see number of 5XXs, 4XXs and 2XXs responses. Especially useful to see if 500s are coming from API (unhandled error) or the ELB (most likely a health or autoscaling thing)
   * Can unhealthy nodes 
   
4. AWS Console Lambda
   * click on multilambda - monitor tab
   * can get to lambda logs from here. Can search lambda logs.
   * Can see lambda throttling here but often find it easier to see in Cloudwatch Dashboard
   
5. AWS Console Step Functions
	* Can see if any state machines are failing
	* Can monitor progress of downsample by seeing what step it is on
	
6. AWS Console DynamoDB - Tables - Select a Table - Metrics
   * from here you can see if a table is throttling, if it is hitting is write or read capacity

## Things to understand
* Lambda capacity is number of lambda invocations per second * average duration of lambda runtimes.
   * if lambdas have to start waiting on other things like DynamoDB tables or S3, then number of lambdas that can run at a time decreases.
* Redis Max CPU is ~3.0 because redis is single threaded, and the machine being used now has 40 cores
* ingest-client does not use the Redis cache so using it will not effect Redis CPU 


## Scenarios

### Ingest is slow
* Current problems typically arise from the DynamoDB capacity not being high enough (auto-scaling should deal with this!) 
	* The TileIndex in DynamoDB is typically first to throttle.  Check in the
  the console and raise it if needed.
	* idIndex DynamoDB table could be hitting capacity for annotation channels or more likely with our current solution hitting a hot shard.
		* To solve this problem we have temporarily disable idIndex from being used during writes (*THIS SHOULD BE FIXED*)
	* Ingest does not currently handle time time-series data well due to how messages are sharded across Z and T during queue population. It works, but is very slow.
		* A possible solution is to enforce a min/max shard size when spreading messages across lambda during queue population
	* Watch the upload and ingest queues.  
		* The upload queue should be staying at a steady rate in the 10s to 100s in flight. If you see inflight messages begin to stack up the first lambda function is failing!
			* Check the lambda logs to try to see what the error is. Typically it's a dynamoDB throttle that's causing lambda to time out or something like that, since this lambda only does a HEAD operation to get the S3 metadata, and then updates the index	 	
     * The ingest queue should be staying at roughtly 0 with inflight staying around something roughly 16x less than the upload queue inflight message count when in steady state. You will typically see a burst of inflight towards the end of the job as stray chunks all finish uploading
     		*  If you see this queue start to stack up, your ingest lambdas are failing! Check the log to try to debug. Often it's a memory or image loading issue. Make sure the tiles aren't too big (2k x 2k is safe for all data types, can go bigger for 8bit). Make sure the image files can be loaded by Pillow. You can do this by downloading a tile from S3 (you can see the key in the logs)
 
### Ingest stuck.  Upload SQS Queue is finished but the Ingest SQS Queue not moving.
* lambda will only pull a single message off of the ingest queue.  
  * It used to pull off two, but started crashing due to memory filling up.
  * If any lambdas fail now, there will be messages left in the ingest SQS Queue.
  * Solution: Dean created a tool, documented in his last day notes that can send lambdas at a specified rate to an SQS queue.
  
# Causes of problems
* **Redis hitting maximum CPU**.  This causes the endpoints to slow down.  It can cause more endpoints to be created without actually helping elevate the problem.  Solution here is to have poeple start using the new no-cache option when querying. Also future design updates and optimization (like not doing a KEY XXX* operation when checking if a key exists) will help this.
* **Too much activity** can tip over the system and cause WRITE-LOCKs to occur.  
   * The first sign of this is that lambda during times is not staying 
constant, it means things could start getting bad.  Look for the bottleneck, is a dynamoDB table hitting capcity of throttling?  If we can not fix the problem, we need to lower the number concurrent nodes performers are using to write.  Sometimes we pause the performers for the system to catch up during heavy use.





  
