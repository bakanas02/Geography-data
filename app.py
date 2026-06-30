import os
import pyodbc
import hashlib
from flask import Flask, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv

# 1. Загружаем переменные из .env файла в окружение
load_dotenv()

app = Flask(__name__)

# 2. Устанавливаем секретный ключ из .env (с запасным вариантом для разработки)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key_only_for_local_testing')

# 3. Получаем данные подключения из .env
server = os.environ.get('DB_SERVER')
database = os.environ.get('DB_NAME')
username = os.environ.get('DB_USER')
password = os.environ.get('DB_PASSWORD')

# 4. Настраиваем соединение с БД
# Используем f-строку для чистоты кода
conn_str = f'DRIVER={{SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}'

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    print("Успешное подключение к базе данных!")
except Exception as e:
    print(f"Ошибка подключения к базе данных: {e}")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = hash_password(password)

        cursor.execute('SELECT * FROM Users WHERE username = ? AND password_hash = ?', (username, password_hash))
        user = cursor.fetchone()

        if user:
            session['username'] = username
            session['is_admin'] = (user.role == 'admin')  # Set is_admin based on user role
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')  # Display error message
            return redirect(url_for('login'))  # Redirect back to login page

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = hash_password(password)

        cursor.execute('SELECT * FROM Users WHERE username = ?', (username,))
        existing_user = cursor.fetchone()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'error')
            return redirect(url_for('register'))

        cursor.execute('INSERT INTO Users (username, password_hash, role) VALUES (?, ?, ?)',
                       (username, password_hash, 'admin'))  # Assigning admin role by default
        conn.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/')
def index():
    if 'username' in session:
        cursor.execute('SELECT * FROM Location')
        locations = cursor.fetchall()

        trigger_logs = []
        if 'added_location' in session:
            trigger_logs.append('Data has been inserted into the Location table.')
            session.pop('added_location', None)
        if 'updated_location' in session:
            trigger_logs.append('Data has been updated in the Location table.')
            session.pop('updated_location', None)
        if 'deleted_location' in session:
            trigger_logs.append('Data has been deleted from the Location table.')
            session.pop('deleted_location', None)

        flash('You are logged into the application web', 'info')
        return render_template('index.html', locations=locations, trigger_logs=trigger_logs)
    else:
        return redirect(url_for('login'))


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))



@app.route('/add_location', methods=['POST'])
def add_location():
    if 'username' not in session:
        flash('You need to log in first', 'error')
        return redirect(url_for('login'))

    if not session.get('is_admin'):
        flash('Only admins can add locations', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form['name']
        latitude_str = request.form['latitude']
        latitude = float(latitude_str.replace(',', '.'))
        longitude_str = request.form['longitude']
        longitude = float(longitude_str.replace(',', '.'))
        country = request.form['country']
        region = request.form['region']
        continent = request.form['continent']

        cursor.execute(
            'INSERT INTO Location (Latitude, Longitude, Name, Country, Region, Continent) VALUES (?, ?, ?, ?, ?, ?)',
            (latitude, longitude, name, country, region, continent))
        conn.commit()

        flash('Location added successfully!', 'success')

        session['added_location'] = True

        return redirect(url_for('index'))


@app.route('/delete_location/<int:location_id>', methods=['POST'])
def delete_location(location_id):
    try:
        if not session.get('is_admin'):
            flash('Only admins can delete locations', 'error')
            return redirect(url_for('index'))

        conn.autocommit = False

        cursor.execute('SELECT * FROM Location WHERE LocationID = ?', (location_id,))
        location = cursor.fetchone()
        if not location:
            flash('Location does not exist', 'error')
            return redirect(url_for('index'))

        cursor.execute('DELETE FROM Climate WHERE LocationID = ?', (location_id,))

        cursor.execute('DELETE FROM NaturalFeatures WHERE LocationID = ?', (location_id,))

        cursor.execute('DELETE FROM Population WHERE LocationID = ?', (location_id,))

        cursor.execute('DELETE FROM Location WHERE LocationID = ?', (location_id,))

        conn.commit()

        conn.autocommit = True

        flash('Location deleted successfully', 'success')
        session['deleted_location'] = True

        return redirect(url_for('index'))

    except pyodbc.DatabaseError as e:
        conn.rollback()
        conn.autocommit = True
        raise e


def get_climate_data(location_id):
    cursor.execute('SELECT * FROM Climate WHERE LocationID = ?', (location_id,))
    return cursor.fetchall()


def get_natural_features_data(location_id):
    cursor.execute('SELECT * FROM NaturalFeatures WHERE LocationID = ?', (location_id,))
    return cursor.fetchall()


def get_population_data(location_id):
    cursor.execute('SELECT * FROM Population WHERE LocationID = ?', (location_id,))
    return cursor.fetchall()


# Add route for editing a location
@app.route('/edit_location/<int:location_id>', methods=['GET', 'POST'])
def edit_location(location_id):
    if 'username' not in session:
        flash('You need to log in first', 'error')
        return redirect(url_for('login'))

    if not session.get('is_admin'):
        flash('Only admins can edit locations', 'error')
        return redirect(url_for('index'))

    if request.method == 'GET':
        cursor.execute('SELECT * FROM Location WHERE LocationID = ?', (location_id,))
        location = cursor.fetchone()

        climate_data = get_climate_data(location_id)
        natural_features_data = get_natural_features_data(location_id)
        population_data = get_population_data(location_id)

        return render_template('edit_location.html', location=location,
                               climate_data=climate_data, natural_features_data=natural_features_data,
                               population_data=population_data)
    elif request.method == 'POST':
        name = request.form['name']
        latitude_str = request.form['latitude']
        latitude = float(latitude_str.replace(',', '.'))
        longitude_str = request.form['longitude']
        longitude = float(longitude_str.replace(',', '.'))
        country = request.form['country']
        region = request.form['region']
        continent = request.form['continent']

        cursor.execute(
            'UPDATE Location SET Name=?, Latitude=?, Longitude=?, Country=?, Region=?, Continent=? WHERE LocationID=?',
            (name, latitude, longitude, country, region, continent, location_id))
        conn.commit()
        session['updated_location'] = True

        climate_data = get_climate_data(location_id)
        natural_features_data = get_natural_features_data(location_id)
        population_data = get_population_data(location_id)

        temperature = request.form['temperature']
        precipitation = request.form['precipitation']
        humidity = request.form['humidity']
        if climate_data:
            cursor.execute('UPDATE Climate SET Temperature=?, Precipitation=?, Humidity=? WHERE LocationID=?',
                           (temperature, precipitation, humidity, location_id))
        else:
            cursor.execute('INSERT INTO Climate (LocationID, Temperature, Precipitation, Humidity) VALUES (?, ?, ?, ?)',
                           (location_id, temperature, precipitation, humidity))
        conn.commit()

        feature_type = request.form['feature_type']
        feature_name = request.form['feature_name']
        feature_description = request.form['feature_description']
        # Check if natural features data exists
        if natural_features_data:
            cursor.execute('UPDATE NaturalFeatures SET FeatureType=?, Name=?, Description=? WHERE LocationID=?',
                           (feature_type, feature_name, feature_description, location_id))
        else:
            cursor.execute(
                'INSERT INTO NaturalFeatures (LocationID, FeatureType, Name, Description) VALUES (?, ?, ?, ?)',
                (location_id, feature_type, feature_name, feature_description))
        conn.commit()

        population_count = request.form['population_count']
        urban_population = request.form['urban_population']
        rural_population = request.form['rural_population']
        # Check if population data exists
        if population_data:
            cursor.execute(
                'UPDATE Population SET PopulationCount=?, UrbanPopulation=?, RuralPopulation=? WHERE LocationID=?',
                (population_count, urban_population, rural_population, location_id))
        else:
            cursor.execute(
                'INSERT INTO Population (LocationID, PopulationCount, UrbanPopulation, RuralPopulation) VALUES (?, ?, ?, ?)',
                (location_id, population_count, urban_population, rural_population))
        conn.commit()

        return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)
