IF NOT EXIST images mkdir images
IF NOT EXIST images/crop mkdir images/crop
python -m venv venv
call ./venv/Scripts/activate.bat
python -m pip install -r requirements.txt -r requirements_dev.txt