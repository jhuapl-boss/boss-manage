# Generating HTML Documentation

`$BOSSMNG` is the location of the boss repository.

```shell
cd $BOSSMNG/docs/SphinxDocs

# Ensure Sphinx and the ReadTheDocs theme is available.
pip3 install -r requirements.txt

./makedocs.sh
```

Documentation will be placed in `$BOSSMNG/docs/SphinxDocs/_build/html`.
