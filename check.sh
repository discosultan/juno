set -e

echo "Checking:"

echo "$ isort --check-only ."
isort --check-only .

echo "$ black --check ."
black --check .

echo "$ flake8 ."
flake8 .

echo "$ mypy ."
mypy .

echo "$ pytest ."
pytest .

echo "All good!"
