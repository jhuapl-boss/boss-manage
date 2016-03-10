base:
  '*':
    - scalyr

  'endpoint*':
    - endpoint

  'proofreader-web*':
    - proofreader-web

  # Jenkins server for Django proofreader tests.
  'pr-jenkins*':
    - proofreader-jenkins

  # Jenkins server for Python scripts such as those in boss-tools.
  'jenkins*':
    - jenkins
