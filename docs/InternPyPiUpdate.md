# Deploying `intern` to PyPI

This should be done in sync with production updates that change the API. 

## Update Version
First you must be sure that the version has been updated. This needs to be done in two places

1. setup.py - change line 11 `__version__ = 'X.X.X'` to the appropriate version
2. intern/\_\_init__.py - change line 5 `version = "X.X.X"` to the appropriate version
 

## Generate Docs
Currently we're using the python package `pdoc` to create very simple docs and host them on ghpages.  To update the docs you must install this package into your virual environment.  Python 2 is recommended for this.

```
pip install -r docs_requirements.txt
```

Then generate the docs using the script `gendocs`.  It's safe to delete the `docs/` directory before running the script as they are completely re-created:

```
export PYTHONPATH=$PYTHONPATH:~/intern
pdoc intern --html --html-dir="docs" --overwrite --docstring-style=google
mv ./docs/intern/* ./docs/
rm -rf ./docs/intern
```

Once pushed to master, the website will automatically be updated.


## Publish to PyPI

Once these are complete and committed, you can update the pip package.

You must have the `twine` package installed in your virtual environment.  Then execute the following commands:

```
python setup.py sdist
python setup.py bdist_wheel
twine upload dist/*
```

Contact @dkleissa for the username and password for the pypi account that is required to publish the updated package.