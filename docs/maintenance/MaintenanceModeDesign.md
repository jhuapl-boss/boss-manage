# Maintenance Mode Design Document

## Components Used
* S3 Bucket in production account: maintenance-prod-boss
* CloudFront Distributions for api.integration.theboss.io and api.theboss.io
* Changes Route53 CNAMES for api.integration.theboss.io and api.theboss.io

## Design Approach
* S3 Bucket is setup as a static web page.  It contains a single file index.html
* CloudFront Distribution is created using the S3 Bucket web page for its backend.  
* The Distribution is setup to use the SSL Certificate from Amazon Certificate Manager
* Customer Error Responses are created for 403 and 404 errors to automatically route to /index.html with a 200 response
* maintenance.py script was created to change Route53 to use the CloudFront Distribution during Maintenance windows.

## Costs
CloudFront distributions only cost for when they are used.  There are not flat fees associated with them.  The costs 
are based on useable by the TB: $0.085.  Our cost per month will be less then 1 TB.  

## Installation procedures
One time installation:
### Create a bucket
go to S3 in the AWS console.
In our case we are using bucket *maintenance-prod-boss*. Upload a simple webpage, index.html, explaining we are down for maintenance.

In bucket properties, Under Permissions:  **Edit or Add bucket policy** 
paste in the follow, being sure to change the buckect name listed below as needed. 
 
 ```bucketpolicy
{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Sid": "PublicReadGetObject",
			"Effect": "Allow",
			"Principal": {
				"AWS": "*"
			},
			"Action": "s3:GetObject",
			"Resource": "arn:aws:s3:::maintenance-prod-boss/*"
		}
	]
}
```
In bucket properties, under Static Web Hosting
* Enable Website Hosting
* Add index.html as the default document

### CloudFront Distributions
Go to CloudFront in AWS console.
Create a new distribution:
* Under *Web* press "Get Started"  
A new dialog "Create Distribution" will come up.
* Origin Domain Name: select your bucket: maintenance-prod-boss.s3.amazonaws.com
*  Viewer Protocol Policy: select HTTP and HTTPS
Distribution Settings:
* Price Class: Use Only US, Canada and Europe
* Alternate Domain Names (CNAMES): api.theboss.io
* SSL Certificate: Select *Custom SSL Certificate* and select the cert for api.theboss.io
* Default Root Object: index.html
Press button **Create Distribution** 

You will see it takes up to an hour to complete the progress.
We can now create error pages, we don't have to wait for the progress to complete.
* Select the new distrbution and press **Distribution Settings"
* Select *Error Pages* Tab
* Press **Create Custom Error Response**
* HTTP Error Code: 403: Forbidden
* Error Caching Minimum TTL (seconds): 10
* Customize Error Response: Yes
* Response Page Path: /index.html
* HTTP response Code:  200: OK
* press *Create*

Create another response code with the same settings except for Error Code: **404: Not Found**
You are done setting up a CloudFront Distribution for *api.theboss.io*

Now walk through the CloudFront Distribution settings and create a new one for *api.integration.theboss.io*

Both Distributions can share the same S3 Bucket.  We create a second one so it can use the correct SSL Certificate.

## Turning on Maintenance Mode
Under the boss-manage/bin directory is *maintenance.py* script.
This can be used 

python3 maintenance.py on production.boss 
python3 maintenance.py off production.boss

python3 maintenance.py on integration.boss
python3 maintenance.py off integration.boss

Turning on or off will change the api CNAME in Route 53.  It may take up to 10 minutes for the change to propagate.  
You can test if it is completed by using the dig command.
```shell
$ dig api.theboss.io
```
It will show either the address of the CloudFront or address of Elastic Load Balancer.





 

