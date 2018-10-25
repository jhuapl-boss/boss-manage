# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

###########################
# S3 Bucket Life Cycle Tags

# Delete tags mark an S3 object for deletion by a life cycle policy.  For
# ingest, lambdas use this name-value pair to mark an object for eventual
# deletion.  They don't delete the object immediately so that idempotentness
# is maintained.  These lambdas are triggered by uploads to the S3 buckets
# which are in turn triggered by SQS messages.  When an SQS message is
# delivered multiple times, problems occured when deleting immediately.
TAG_DELETE_KEY = "delete"
TAG_DELETE_VALUE = "true"
