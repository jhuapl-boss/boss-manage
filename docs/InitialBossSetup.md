# Initial Bosslet Setup

## Setting up the public domain

* Purchase a domain name, externally or through Route53
* Add it to Route53, so that Route53 manages the DNS records for the domain name
* Request a wildcard certificate `*.domain.tld`, either externally or using Amazon Certificate Manager (ACM)
  - Using Domain validation is the easier, and suggested, approach if using ACM. There should be a link after requesting the certificate in ACM.
  - If you don't want to get a wildcard certificate you need to request `api.domain.tld` and `auth.domain.tld` certificates. If you plan to run multiple Bosslets under the given domain then the certificates will be something _like_ `api.sub.domain.tld` and `auth.sub.domain.tld`, though you can modify the Bosslet configuration `EXTERNAL_FORMAT` value to be whatever you want.
* Wait until the certificate request has been verificated and the SSL certificate is issued
  - If you used ACM then you don't need to do anything else
  - If you requested the certificate externally you need to import the certificate and private key into ACM so that AWS resources can use the SSL certificate

Any Bosslet using the domain can now lookup the certificate(s) needed and attach them to the load balancers to provide HTTPS traffic
