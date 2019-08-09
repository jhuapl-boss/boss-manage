# Deploying `intern` to PyPI

This should be done in sync with production updates that change the API. 

## Update Version
First you must be sure that the version has been updated.


intern/\_\_init__.py - change the line `version = "X.X.X"` to the appropriate version

Update the CHANGELOG.md to reflect the new features / bug fixes.
 

## Generate Docs
Currently we're using the python package `pdoc` to create very simple docs and host them on ghpages.  To update the docs you must install this package into your virual environment.  Python 2 is recommended for this.

```
pip install -r docs_requirements.txt
```

Then generate the docs using the script `gendocs`.  It's safe to delete the `docs/` directory before running the script as they are completely re-created:

If you don't already have a PYTHONPATH remove the : from the line in the box:

```
export PYTHONPATH=$PYTHONPATH:~/intern
mv docs docs-old
pdoc intern --html --html-dir="docs" --overwrite --docstring-style=google
mv ./docs/intern/* ./docs/
rm -rf ./docs/intern
rm -rf docs-old
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

