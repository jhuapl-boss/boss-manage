include:
  - jenkins
  - jenkins.cli

{% from "jenkins/map.jinja" import jenkins with context %}

{%- macro fmtarg(prefix, value)-%}
{{ (prefix + ' ' + value) if value else '' }}
{%- endmacro -%}
{%- macro jenkins_cli(cmd) -%}
{{ ' '.join(['java', '-jar', jenkins.cli_path, '-s', jenkins.master_url, fmtarg('-i', jenkins.get('privkey')), cmd]) }} {{ ' '.join(varargs) }}
{%- endmacro -%}

jenkins_slack:
  file:
    - managed
    - source: {{ jenkins.slack }}
    - name: {{ jenkins.home }}/jenkins.plugins.slack.SlackNotifier.xml
    - user: {{ jenkins.user }}
    - group: {{ jenkins.group }}
    - mode: 644
    - timeout: 60
    - require:
      - service: jenkins
      - cmd: jenkins_cli_jar
    - watch_in:
      - cmd: restart_jenkins
