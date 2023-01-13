set -e

echo "Checking:"

echo "$ black --check ."
black --check .

echo "$ isort --check-only ."
isort --check-only .

echo "$ flake8 ."
flake8 .

echo "$ mypy ."
mypy .

echo "$ pytest ."
pytest .

echo "All good!"
