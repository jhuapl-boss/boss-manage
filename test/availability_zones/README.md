# Availability Zone Tests
Not every availability zone (AZ) within a region can support every service that AWS provides. The problem is that for any given AWS account the AZ assignment is randomized, so the `A` AZ on one account may work for a service but may not work for another account. These assignments are statis and should not change.

The scripts in this folder will attempt to create AWS resources (via Cloud Formation) to discover if there are limitations for the given resource. These were initially discovered manually in the us-east-1 region and the scripts are designed to allow other deployments to the us-east-1 region or other regions to discover their own limitations. In addition the scripts can be used to see if AWS has removed the limitations that we initially discovered

## Lambda
Due to the large number of lambdas that get launched that need internal VPC access a reserved set of lambda subnets are created. These subnets are available exclusivly for lambdas to attach their network interface to, so as to get an internal IP and network connection.

## ASG

## Data Pipelines
