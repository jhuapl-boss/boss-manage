python3:
    pkg:
        - installed

python3-pip:
    pkg:
        - installed
        - require:
            - pkg: python3
            
python2.7:
    pkg:
        - installed
        
python-pip:
    pkg:
        - installed