base:
  '*':
    - scalyr

  'endpoint*':
    - endpoint
    - chrony

  'cachemanager*':
    - cachemanager
    - chrony

  'activities*':
    - activities
    - chrony

  'ep-jenkins*':
    - endpoint-jenkins

  'proofreader-web*':
    - proofreader-web
    - chrony

  # Jenkins server for Django proofreader tests.
  'pr-jenkins*':
    - proofreader-jenkins

  # Jenkins server for Python scripts such as those in boss-tools.
  'jenkins*':
    - jenkins