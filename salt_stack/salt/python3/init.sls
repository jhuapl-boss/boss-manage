python3:
    pkg:
        - installed

python3-pip:
    pkg:
        - installed
        - require:
            - pkg: python3