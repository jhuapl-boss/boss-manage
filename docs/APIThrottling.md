# API Throttling Capability
This capability provides for throttling at the bossdb API layer.
Not to be confused with AWS throttling that bossdb also supports. 

# Overview
API Throttling is enforced when users or applications invoke APIs that move data or otherwise incur costs for the AWS account. Each API can check for limits by using the BossThrottle.check() method from within a view. 

## Metric Types
There are 3 metric types supported: Ingress (bytes), Egress (bytes), and Compute (cuboids). Each API determines the metric type (mtype) and units used when performing a check. Each metric type has default limits for each level of throttling (see Thresholds).

## Thresholds
Each threshold object is uniquely identified by a name and metric type.  The naming of the metric reflects level of the limit: system, api, or user. For example, there is a system level threshold for each possible metric type. Each threshold has limit setting. 

## Usage
For every threshold, there is a usage object that tracks the current usage level and the date since that usage has been aggregated. When usage is checked, the aggregated usage will be reset to 0 if the current aggregation is for the previous month. In other words, the usage is reset to zero at the start of each month.



