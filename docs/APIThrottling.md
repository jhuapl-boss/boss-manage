# API Throttling Capability
This capability provides for throttling at the bossdb API layer.
Not to be confused with AWS throttling that bossdb also supports. 

# Overview
API Throttling is enforced when users or applications invoke APIs that move data or otherwise incur costs for the AWS account. Each API can check for limits by using the BossThrottle.check() method from within a view. 

## Metric Types
Each data API determines the __metric type__ (mtype) and units reported when performing a throttling check.
Currently, there are 3 metric types defined by the boss APIs: _ingress_, _egress_, and _compute_.  Each metric type has default limits for each level of throttling (see Thresholds). The units for the metric types are fixed by the APIs.

## Thresholds
Each __threshold__ object is uniquely identified by a __metric name__ and __metric type__.  The naming of the metric reflects the scope of the limit: _system_, _api_, or _user_. For example, the user johnsmith will have thresholds with metric name \"user:johnsmith\" and the cutout api will have thresholds with metric name \"api:cutout\". Thresholds for the __system__ level will have metric names \"system\". Each threshold has an integer __limit__ value. A limit of -1 will disable thresholding for this metric (name and type).

## Usage
For every threshold, there is a usage object that tracks the current usage level. The __value__ field is the aggregated usage. The __since__ field is the date since that usage has been aggregated. When usage is checked, the aggregated value will be cleared and the since field will be updated if the current aggregation is for the previous month. In other words, the usage is reset to zero at the start of each month. However, the value is only reset when a throttle check is made. Using the API to read the usage will not change it.

# Initialization
After an initial deployment, there will be no __metric types__ or __thresholds__ defined. As API calls are made, metric types, thresholds, and usage objects will be created automatically. By default, all thresholds are set to unlimited so no throttling will occur. An administrator can set the default limits using the REST API before allowing users access. This will cause automatically created thresholds to use the new default limits for metrics. 

# REST API
The metric API allows administrators to view metric types, thresholds, and usage objects. Non-admin users can only view their own usage objects. Administrators can create and update metric types and thresholds. A metric type can be updated to change the default limit for newly created thresholds. A threshold object can be updated to change the limit and allow a user to continue working.

## Metric Types
Each metric type has defaults for system, api, and user level metrics. A limit of -1 means there is no limit.

Metric types can be read by an administrator using a GET https://_api-fqdn_/metric/metrics. Sample results are shown below:

```json
[ {"mtype":"egress",
   "units":"byte_count",
   "def_user_limit":5368709120,
   "def_api_limit":-1,
   "def_system_limit":-1},
  {"mtype":"ingress",
   "units":"byte_count",
   "def_user_limit":10737418240,
   "def_api_limit":-1,
   "def_system_limit":-1} ]
```

In the above example, there are two metric types defined. The egress metric has a default user limit of 5G and the ingress metric has a default user limit of 10G. The default for system and api scope is unlimited.

Metric types can be created or updated using a PUT to https://_api-fqdn_/metric/metrics. The only required field is __mtype__. The default limits are optional. The units field will be ignored. Sample data for a PUT is shown below:

```json
[{"mtype":"egress", "def_user_limit":"10G"}]
```
In our sample data, the default user limit for the egress metric type will be changed to 10G. The PUT command for /metric/metrics accepts strings or integer values for a limit. The string must be a number followed by an optional scalar: K, M, G, or T. Upper or lowercase is accepted.

## Thresholds
The thresholds can be read by an administrator using a GET https://_api-fqdn_/metric/thresholds. An example is shown below:

```json
[ {"metric":"user:bossadmin",
   "mtype":"egress",
   "units":"byte_count",
   "limit":5368709120},
  {"metric":"api:cutout",
   "mtype":"egress",
   "units":"byte_count",
   "limit":-1} ]
```
An adminstrator can create or update thresholds using a PUT https://_api-fqdn_/metric/thresholds. There are two required fields: _metric_ and _mtype_. The _limit_ field is optional. If the threshold does not exist, it will be created and the limit will be set to the default for that metric type. An example is shown below:

```json
[ {"metric":"user:bossadmin",
   "mtype":"egress",
   "limit":"10G"}, ]
```
In the above example, the "user:bossadmin" _egress_ limit will be changed to 10G. 

## Usage
Finally, any user can read their usage by using a GET https://_api-fqdn_/metric/. This will show the usage for the current user. An example is shown below:

```json
[ {"metric":"user:bossadmin",
   "mtype":"egress",
   "units":"byte_count",
   "limit":5368709120,
   "since":"2020-10-21",
   "value":8},
  {"metric":"user:bossadmin",
   "mtype":"ingress",
   "units":"byte_count",
   "limit":10737418240,
   "since":"2020-10-21",
   "value":1000000} ]
```

An administrator can view the usage for any metric by using a GET https://_api-fqdn_/metric/?metric=_metricname_. And the adminsistrator can get all usage data by using a GET https://_api-fqdn_/metric/usage.

