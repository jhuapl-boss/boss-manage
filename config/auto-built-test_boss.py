#
# BOSS Configuration File for the auto build testing process
# This will be used by an EC2 instance to build a new stack
# and run all of the integration tests
# Resources will be names *.test.boss
#

EXTERNAL_DOMAIN = "thebossdev.io"
EXTERNAL_FORMAT = "{machine}-test"
INTERNAL_DOMAIN = "test.boss"
NETWORK = "10.20.0.0/16"

AMI_SUFFIX = ".boss"
SCENARIO = "development"

REGION = "us-east-1"
AVAILABILITY_ZONE_USAGE = {
    'lambda': ['b', 'c', 'd', 'e', 'f'],
    'asg': ['b', 'c', 'd', 'e', 'f'],
    'datapipeline': ['a', 'b', 'c', 'd', 'f'],
}

AUTH_RDS = False

LAMBDA_BUCKET = "boss-lambda-env"
LAMBDA_SERVER = "52.23.27.39"
LABMDA_SERVER_KEY = 'microns-bastion20151117'

ACCOUNT_ID = 256215146792
PROFILE = None # Use EC2 credentials

OUTBOUND_BASTION = False

# Get the local IP of the EC2 instance, so that the machine can
# interact with the stack it is standing up, but no one else can
import urllib.request
META_URL = "http://169.254.169.254/latest/meta-data/public-ipv4"
LOCAL_IP = urllib.request.urlopen(url).read().decode("utf-8")

HTTPS_INBOUND = LOCAL_IP + "/32"
SSH_INBOUND = LOCAL_IP + "/32"
SSH_KEY = "auto-build-keypair"
