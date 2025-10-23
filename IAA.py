import telebot
import cv2
import numpy as np
import requests
from telebot import types
import re
import sqlite3
import uuid
import requests
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import io
from email.mime.image import MIMEImage
import base64
import os
from dotenv import load_dotenv
load_dotenv()

count = 0
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
user_categories = {}
active_apps = {}
user_photos = {}  # Временное хранение фото перед сохранением в БД

flag_country = [
    ("🇷🇺 Россия", "rus"), ("🇺🇸 США", "usa"), ("🇪🇸 Испания", "esp"), ("🇫🇷 Франция", "fr"),
    ("🇵🇹 Португалия", "port"), ("🇹🇷 Турция", "tur"), ("🇻🇳 Вьетнам", "viet"), ("🇨🇳 Китай", "chi"),
    ("🇦🇪 ОАЭ", "arab"), ("🇦🇲 Армения", "arm")
]

country_mapping = {
    "rus": "Россия", "usa": "США", "esp": "Испания", "fr": "Франция",
    "port": "Португалия", "tur": "Турция", "viet": "Вьетнам", "chi": "Китай",
    "arab": "ОАЭ", "arm": "Армения"
}

categor = [
    ("A", "A"), ("A1", "A1"), ("B", "B"), ("C", "C"), ("D", "D"),
    ("BE", "BE"), ("CE", "CE"), ("DE", "DE"), ("B1", "B1"), 
    ("M", "M"), ("D1E", "D1E"), ("C1E", "C1E")
]

# Настройки email (замените на реальные)
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'email': os.getenv("EMAIL_USER"),
    'password': os.getenv("EMAIL_PASSWORD"),
    'use_ssl': True
}

# Подключение к базе данных
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицу для заявок с полем для фото
cursor.execute('''CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT,
    fio TEXT,
    date_birth TEXT,
    country TEXT,
    categories TEXT,
    license_number TEXT,
    license_issue_date TEXT,
    email TEXT,
    photo_blob BLOB,
    photo_format TEXT,
    status TEXT DEFAULT 'draft',
    payment_method TEXT,
    payment_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()


def pay_yookassa(message, amount=1000):
    """Оплата через ЮKassa """
    try:
        shop_id = "key_id"  # Shop ID из ЮKassa
        secret_key = "key"  # Secret Key из ЮKassa
        
        order_id = str(uuid.uuid4())
        
        headers = {
            "Content-Type": "application/json",
            "Idempotence-Key": order_id
        }
        
        data = {
            "amount": {
                "value": str(amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/@IntAuto_bot"  
            },
            "capture": True,
            "description": f"Оплата международного водительского удостоверения"
        }
        
        response = requests.post(
            "https://api.yookassa.ru/v3/payments",
            auth=(shop_id, secret_key),
            headers=headers,
            json=data,
            timeout=10
        )
        
        payment = response.json()
        if "confirmation" in payment:
            url = payment["confirmation"]["confirmation_url"]
            user_id = message.from_user.id
            update_application(user_id, "payment_method", "yookassa")
            update_application(user_id, "payment_status", "waiting")
            
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton('✅ Я оплатил', callback_data='check_payment')
            markup.add(btn)
            
            bot.send_message(message.chat.id, 
                           f"💳 Сумма к оплате: {amount} руб.\n"
                           f"🔗 Перейдите по ссылке для оплаты: {url}\n"
                           f"После оплаты нажмите кнопку ниже",
                           reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при создании платежа")
            
    except Exception as e:
        print(f"Ошибка ЮKassa: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при создании платежа")

def pay_lava(message, amount=1000):
    """Оплата через Lava (требует настройки реальных ключей)"""
    try:
        # ЗАМЕНИТЕ НА РЕАЛЬНЫЕ ДАННЫЕ!
        api_key = "key"
        shop_id = "key"
        order_id = str(uuid.uuid4())
        
        data = {
            "shopId": shop_id,
            "amount": amount,
            "orderId": order_id,
            "currency": "RUB",
            "returnUrl": f"https://t.me/@IntAuto_bot"
        }
        
        headers = {"Authorization": f"Bearer {api_key}"}
        
        response = requests.post("https://api.lava.ru/invoice", json=data, headers=headers, timeout=10)
        result = response.json()
        
        if "url" in result:
            user_id = message.from_user.id
            update_application(user_id, "payment_method", "lava")
            update_application(user_id, "payment_status", "waiting")
            
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton('✅ Я оплатил', callback_data='check_payment')
            markup.add(btn)
            
            bot.send_message(message.chat.id, 
                           f"💳 Сумма к оплате: {amount} руб.\n"
                           f"🔗 Оплатите по ссылке: {result['url']}\n"
                           f"После оплаты нажмите кнопку ниже",
                           reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при создании платежа")
            
    except Exception as e:
        print(f"Ошибка Lava: {e}")
        bot.send_message(message.chat.id, "❌ Произошла ошибка при создании платежа")

def simulate_payment(message, amount=1000):
    """Симуляция оплаты для тестирования (удалите в продакшене)"""
    user_id = message.from_user.id
    update_application(user_id, "payment_method", "test")
    update_application(user_id, "payment_status", "completed")
    update_application(user_id, "status", "paid")
    
    bot.send_message(message.chat.id, 
                   "✅ Тестовая оплата прошла успешно!\n"
                   "📋 Ваша заявка принята в обработку.\n"
                   "⏳ Срок изготовления: 1-3 рабочих дня")

    
def create_new_application(user_id):
    """Создает новую заявку и возвращает её ID"""
    cursor.execute("INSERT INTO applications (user_id, status) VALUES (?, 'draft')", (user_id,))
    conn.commit()
    app_id = cursor.lastrowid
    active_apps[user_id] = app_id
    user_categories[user_id] = []
    return app_id

def update_application(user_id, field, value):
    """Обновляет поле в активной заявке пользователя"""
    app_id = active_apps.get(user_id)
    if app_id:
        cursor.execute(f"UPDATE applications SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", 
                      (value, app_id))
        conn.commit()

def save_photo_to_db(user_id, image_data, format='jpeg'):
    """Сохраняет фотографию в базу данных"""
    app_id = active_apps.get(user_id)
    if app_id:
        try:
            # Конвертируем изображение в байты
            if isinstance(image_data, np.ndarray):
                # Если это numpy array (после OpenCV обработки)
                success, encoded_image = cv2.imencode(f'.{format}', image_data)
                if success:
                    photo_bytes = encoded_image.tobytes()
                else:
                    return False
            else:
                # Если это уже байты
                photo_bytes = image_data
            
            # Сохраняем в базу данных
            cursor.execute("UPDATE applications SET photo_blob = ?, photo_format = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", 
                          (photo_bytes, format, app_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Ошибка сохранения фото в БД: {e}")
            return False
    return False

def get_photo_from_db(app_id):
    """Получает фотографию из базы данных"""
    try:
        cursor.execute("SELECT photo_blob, photo_format FROM applications WHERE id = ?", (app_id,))
        result = cursor.fetchone()
        if result and result[0]:
            return result[0], result[1]  # blob_data, format
        return None, None
    except Exception as e:
        print(f"Ошибка получения фото из БД: {e}")
        return None, None

def send_confirmation_email(email, user_data, photo_data=None):
    """Отправка подтверждающего email с данными заявки и фото"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = email
        msg['Subject'] = 'Подтверждение заявки на международное водительское удостоверение'
        
        body = f"""
        Уважаемый(ая) {user_data['fio']},
        
        Ваша заявка на международное водительское удостоверение успешно принята!
        
        Детали заявки:
        - ФИО: {user_data['fio']}
        - Дата рождения: {user_data['date_birth']}
        - Страна: {user_data['country']}
        - Категории: {user_data['categories']}
        - Номер лицензии: {user_data['license_number']}
        - Дата выдачи: {user_data['license_issue_date']}
        
        Статус заявки: В обработке
        Ориентировочный срок изготовления: 3-5 рабочих дней
        
        После изготовления удостоверения мы отправим его по указанному адресу.
        
        С уважением,
        Служба поддержки
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Если есть фото, прикрепляем его к письму
        if photo_data:
            try:
                photo_bytes, photo_format = photo_data
                attachment = MIMEImage(photo_bytes, _subtype=photo_format)
                attachment.add_header('Content-Disposition', 'attachment', filename=f'photo.{photo_format}')
                msg.attach(attachment)
            except Exception as e:
                print(f"Ошибка прикрепления фото к email: {e}")
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Ошибка отправки email: {e}")
        return False

@bot.message_handler(commands=['start'])
def start(message):
    # Сохраняем информацию о пользователе
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    

    
    # Создаем новую заявку
    create_new_application(user_id)
    
    with open('Intro.txt', 'r', encoding='utf-8') as file:
        text = file.read()
    
    bot.send_message(message.chat.id, text)
    bot.send_message(message.chat.id, "Давайте начнем работу. Загрузите фотографию согласно следующим"
                     "требованиям:  Поддерживаемые форматы: jpeg, png;\nЦвет фона: белый, монохромный;\n"
                     "Размер: не меньше 400 x 500px.")
    bot.register_next_step_handler(message, handle_photo)

def handle_photo(message):
    global count
    count += 1
    
    if message.text == "🔄 Начать заново":
        bot.register_next_step_handler(message, start)
        return
        
    if not message.photo:
        bot.send_message(message.chat.id, "Ошибка: фото не найдено. Пожалуйста, отправьте изображение.")
        bot.register_next_step_handler(message, handle_photo)
        return
        
    # Получаем наибольшую по качеству версию фото
    photo = message.photo[-1]
    file_info = bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
    
    # Загружаем фото
    try:
        response = requests.get(file_url, timeout=10)  
        img_array = np.frombuffer(response.content, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        # Сохраняем оригинальные байты фото
        original_photo_bytes = response.content
        
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, "Ошибка загрузки изображения.")
        bot.register_next_step_handler(message, handle_photo)
        return

    if img is None:
        bot.send_message(message.chat.id, "Ошибка: неподдерживаемый формат. Пришлите JPEG или PNG.")
        bot.register_next_step_handler(message, handle_photo)
        return

    # Проверка размеров изображения
    h, w = img.shape[:2]
    cropped_img = None
    
    if w < 400 or h < 500:
        bot.send_message(message.chat.id, "Изображение было кропнуто до 500x400.")
        x_center = w // 2
        y_center = h // 2
        x_start = max(0, x_center - 200)
        y_start = max(0, y_center - 250)
        cropped_img = img[y_start:y_start+500, x_start:x_start+400]
        
        # Сохраняем кропнутое изображение во временное хранилище
        user_id = message.from_user.id
        user_photos[user_id] = cropped_img
        
        # Отправляем пользователю preview
        success, encoded_image = cv2.imencode('.jpg', cropped_img)
        if success:
            photo_bytes = encoded_image.tobytes()
            bot.send_photo(message.chat.id, photo_bytes, caption="Вот ваше обработанное фото")
    else:
        # Сохраняем оригинальное изображение во временное хранилище
        user_id = message.from_user.id
        user_photos[user_id] = original_photo_bytes
    
    # Проверка фона изображения
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY)
    white_ratio = np.sum(thresh == 255) / (w * h)
    
    if white_ratio < 0.3:
        bot.send_message(message.chat.id, "Ошибка: фон должен быть белым или монохромным.")
        bot.register_next_step_handler(message, handle_photo)
        return
    
    bot.send_message(message.chat.id, "Фото прошло все проверки ✅")
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_restart = types.KeyboardButton("🔄 Начать заново")
    markup.add(btn_restart)
    
    bot.send_message(message.chat.id, "Введите ФИО", reply_markup=markup)
    bot.register_next_step_handler(message, f_fio)

def f_fio(message):
    user_id = message.from_user.id
    
    if message.text == "🔄 Начать заново":
        create_new_application(user_id)
        bot.send_message(message.chat.id, "Давайте начнем работу. Загрузите фотографию...")
        bot.register_next_step_handler(message, handle_photo)
        return
    
    fio = message.text.split()
    if len(fio) == 3:
        fio_str = " ".join(fio)
        update_application(user_id, "fio", fio_str)
        
        # Сохраняем фото в базу данных после ввода ФИО
        if user_id in user_photos:
            photo_data = user_photos[user_id]
            if isinstance(photo_data, np.ndarray):
                # Это кропнутое изображение (numpy array)
                save_photo_to_db(user_id, photo_data, 'jpeg')
            else:
                # Это оригинальные байты
                save_photo_to_db(user_id, photo_data, 'jpeg')
            
            # Удаляем из временного хранилища
            del user_photos[user_id]

        bot.send_message(message.chat.id, "Введите дату рождения (ДД.ММ.ГГГГ):")
        bot.register_next_step_handler(message, dateBirth)   
    else:
        bot.send_message(message.chat.id, "Введите фамилию, имя и отчество через пробел!")
        bot.register_next_step_handler(message, f_fio)

# ... остальные функции (dateBirth, handle_country_selection, handle_categories, countryChoose) без изменений ...
def dateBirth(message):
    user_id = message.from_user.id
    
    if message.text == "🔄 Начать заново":
        create_new_application(user_id)
        bot.send_message(message.chat.id, "Давайте начнем работу. Загрузите фотографию согласно следующим"
                     "требованиям:  Поддерживаемые форматы: jpeg, png;\nЦвет фона: белый, монохромный;\n"
                     "Размер: не меньше 400 x 500px.")
        bot.register_next_step_handler(message, handle_photo)
        return
        
    date_pattern = r"^\d{2}\.\d{2}\.\d{4}$"
    
    if re.fullmatch(date_pattern, message.text):
        update_application(user_id, "date_birth", message.text)
        
        markup = types.InlineKeyboardMarkup()
        for i in range(0, len(flag_country), 3):
            markup.row(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in flag_country[i:i+3]])
             
        bot.send_message(message.chat.id, "Выберите страну проживания:", reply_markup=markup)
        
    else:
        bot.send_message(message.chat.id, "Ошибка: введите дату в формате ДД.ММ.ГГГГ.")
        bot.register_next_step_handler(message, dateBirth)

@bot.callback_query_handler(func=lambda callback: callback.data in [i[1] for i in flag_country])
def handle_country_selection(callback):
    user_id = callback.from_user.id
    country_code = callback.data
    print(callback.data)
    # Находим emoji флага по коду
    country_emoji = next((text for text, data in flag_country if data == country_code), "🌍")
    
    update_application(user_id, "country", country_code)
    bot.send_message(callback.message.chat.id, f"Выбрана страна: {country_emoji}")
    
    # Переходим к выбору категорий
    markup = types.InlineKeyboardMarkup()
    for i in range(0, len(categor), 4):
        markup.row(*[types.InlineKeyboardButton(text, callback_data=text) for text, _ in categor[i:i+4]])
    markup.add(types.InlineKeyboardButton("✅ Готово", callback_data="done_categories"))
    
    bot.send_message(callback.message.chat.id, 
                    "Отметьте наличие категорий действующего водительского удостоверения",
                    reply_markup=markup)

@bot.callback_query_handler(func=lambda callback: callback.data in [i[0] for i in categor] + ["done_categories"])
def handle_categories(callback):
    user_id = callback.from_user.id

    if callback.data == "done_categories":
        if user_id in user_categories and user_categories[user_id]:
            cats = ", ".join(user_categories[user_id])
            update_application(user_id, "categories", cats)
            bot.send_message(callback.message.chat.id, f"Вы выбрали категории: {cats}")
            bot.send_message(callback.message.chat.id, "Введите номер оригинальной лицензии водительского удостоверения и дату выдачи (в формате: НОМЕР ДД.ММ.ГГГГ).")
        else:
            bot.send_message(callback.message.chat.id, "Вы пока не выбрали категорий!")
        return

    # Добавляем категорию в список для текущей заявки
    category = callback.data
    if user_id not in user_categories:
        user_categories[user_id] = []
    if category not in user_categories[user_id]:
        user_categories[user_id].append(category)

    bot.answer_callback_query(callback.id, f"Добавлена категория {category}")

@bot.message_handler(func=lambda message: True)
def handle_license_info(message):
    user_id = message.from_user.id
    
    if message.text == "🔄 Начать заново":
        create_new_application(user_id)
        bot.send_message(message.chat.id, "Давайте начнем работу. Загрузите фотографию согласно следующим"
                     "требованиям:  Поддерживаемые форматы: jpeg, png;\nЦвет фона: белый, монохромный;\n"
                     "Размер: не меньше 400 x 500px.")
        bot.register_next_step_handler(message, handle_photo)
        return
    
    # Ожидаем ввод номера лицензии и даты выдачи
    parts = message.text.split()
    if len(parts) >= 2:
        license_number = parts[0]
        license_date = " ".join(parts[1:])
        
        date_pattern = r"^\d{2}\.\d{2}\.\d{4}$"
        
        if len(license_number) >= 5 and re.fullmatch(date_pattern, license_date):
            update_application(user_id, "license_number", license_number)
            update_application(user_id, "license_issue_date", license_date)
            
            # Предлагаем выбор способа оплаты
            markup = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton('Оплата ЮKassa', callback_data='yookassa')
            btn2 = types.InlineKeyboardButton('Оплата LavaTop', callback_data='lava')
            btn3 = types.InlineKeyboardButton('Тестовая оплата', callback_data='test_payment')

            btn4 = types.InlineKeyboardButton('Проверить статус оплаты', callback_data='check_payment')
            markup.row(btn1, btn2, btn3, btn4)

            bot.send_message(message.chat.id, "Выберите способ оплаты:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Неверный формат. Введите номер лицензии и дату выдачи (в формате: НОМЕР ДД.ММ.ГГГГ).")
    else:
        bot.send_message(message.chat.id, "Введите номер лицензии и дату выдачи через пробел (в формате: НОМЕР ДД.ММ.ГГГГ).")

@bot.callback_query_handler(func=lambda callback: callback.data in ["yookassa", "lava", "test_payment", "check_payment"])
def handle_payment_selection(callback):
    user_id = callback.from_user.id
    
    if callback.data == "yookassa":
        pay_yookassa(callback.message)
    elif callback.data == "lava":
        pay_lava(callback.message)
    elif callback.data == "test_payment":
        simulate_payment(callback.message)
    elif callback.data == "check_payment":
        # После подтверждения оплаты запрашиваем email
        bot.send_message(callback.message.chat.id, 
                       "✅ Оплата подтверждена!\n"
                       "📧 Пожалуйста, введите ваш email для отправки удостоверения:")
        bot.register_next_step_handler(callback.message, process_email_input)

def process_email_input(message):
    """Обработка ввода email"""
    user_id = message.from_user.id
    
    if message.text == "🔄 Начать заново":
        create_new_application(user_id)
        bot.send_message(message.chat.id, "Давайте начнем работу. Загрузите фотографию...")
        bot.register_next_step_handler(message, handle_photo)
        return
    
    email = message.text.strip()
    
    # Валидация email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(email_pattern, email):
        # Сохраняем email в базу данных
        update_application(user_id, "email", email)
        update_application(user_id, "status", "completed")
        
        # Получаем данные заявки для отправки email
        app_id = active_apps.get(user_id)
        if app_id:
            cursor.execute("SELECT fio, date_birth, country, categories, license_number, license_issue_date FROM applications WHERE id = ?", (app_id,))
            app_data = cursor.fetchone()
            
            if app_data:
                user_data = {
                    'fio': app_data[0],
                    'date_birth': app_data[1],
                    'country': app_data[2],
                    'categories': app_data[3],
                    'license_number': app_data[4],
                    'license_issue_date': app_data[5]
                }
                
                # Получаем фото из базы данных
                photo_data = get_photo_from_db(app_id)
                
                # Отправляем подтверждающий email с фото
                if send_confirmation_email(email, user_data, photo_data):
                    bot.send_message(message.chat.id, 
                                   "🎉 Заявка оформлена успешно!\n"
                                   f"📧 Подтверждение отправлено на email: {email}\n"
                                   "📋 Ваша заявка принята в обработку.\n"
                                   "⏳ Срок изготовления: 3-5 рабочих дней")
                else:
                    bot.send_message(message.chat.id,
                                   "✅ Заявка оформлена успешно!\n"
                                   "⚠️ Не удалось отправить email с подтверждением.\n"
                                   "📞 Для уточнения деталей свяжитесь с поддержкой.")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при обработке заявки.")
    else:
        bot.send_message(message.chat.id, "❌ Неверный формат email. Пожалуйста, введите корректный email:")
        bot.register_next_step_handler(message, process_email_input)

bot.polling(none_stop=True)
