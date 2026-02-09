rm -rf dist build *.egg-info
python -m build
python -m twine upload dist/seestarpy*

# check C:/Users/<me>/.pypirc for the API token on Altair