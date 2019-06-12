# Initial AWS Account Setup

## AWS IAM Permisions
* Manually create IAM user with API keys and full permissions in AWS
* Create a Bosslet configuration, using `config/boss_config.py.example` as the template
  - To verify that the configuration file is correct and includes the needed values you can run `bin/boss-config.py <bosslet.name>`
* Run `bin/iam_utils.py <bosslet.name> import roles groups policies` to import the initial IAM configuration
* Remove full permissions from the IAM user and add them to the `XXXXXX` IAM group
  - Any other Developer or Maintainer should be added to the `XXXXXX` IAM group so they have the needed permissions to manipulate and work with Boss resources

## Billing Alerts
* Run `bin/boss-account.py <bosslet.name> billing --create --add <email.address@company.tld> --ls` to create billing alarms
  - This requires the optional `BILLING_THREASHOLDS` Bosslet configuration value to be defined
  - This is optional and only needed if you want to receive notification once the AWS monthly bill exceeds the given threashold(s)

## Error Alerts
* Run `bin/boss-account.py <bosslet.name> alerts --create --add <email.address@company.tld> --ls` to create the alerting mailing list
  - This is used by different Boss processes to alert the developer(s) or maintainer(s) that a problem was encountered and attention is needed to resolve it
