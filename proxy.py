from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
import json
import os
import logging
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Файлы для хранения данных
ORDERS_FILE = 'orders.json'
PROXIES_FILE = 'proxies.json'
SETTINGS_FILE = 'settings.json'

# ========== ФУНКЦИИ РАБОТЫ С ФАЙЛАМИ ==========
def load_proxies():
    default_proxies = {'server1': [], 'server2': [], 'server3': []}
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, 'r') as f:
                content = f.read().strip()
                if not content:
                    return default_proxies
                data = json.loads(content)
                return data if data else default_proxies
        except (json.JSONDecodeError, FileNotFoundError):
            return default_proxies
    return default_proxies

def save_proxies(proxies):
    with open(PROXIES_FILE, 'w') as f:
        json.dump(proxies, f, indent=2, ensure_ascii=False)

def load_orders():
    if os.path.exists(ORDERS_FILE):
        try:
            with open(ORDERS_FILE, 'r') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except json.JSONDecodeError:
            logger.error("Файл orders.json повреждён, создаём новый")
            return {}
    return {}

def save_orders(orders):
    with open(ORDERS_FILE, 'w') as f:
        json.dump(orders, f, indent=2, ensure_ascii=False)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
request = HTTPXRequest(
    connection_pool_size=20,
    connect_timeout=30.0,
    read_timeout=30.0,
    pool_timeout=15.0,
    http_version="1.1"
)

app = Application.builder().token(TOKEN).request(request).build()
proxies_pool = load_proxies()
orders = load_orders()
settings = load_settings()

# Тарифы
SUBSCRIPTION_PLANS = {
    'ipv4': {'name': '🇷🇺 IPv4', 'price': 99, 'days': 7, 'server': 'server1'},
    'ipv4_3users': {'name': '👥 IPv4 (до 3 пользователей)', 'price': 219, 'days': 7, 'server': 'server2'},
    'ipv6': {'name': '🌐 IPv6', 'price': 149, 'days': 7, 'server': 'server3'},
    'monthly': {'name': '💎 Месячный (IPv4)', 'price': 349, 'days': 30, 'server': 'server1'}
}

PAYMENT_DETAILS = """
💳 Реквизиты для оплаты:

💳 Т-Банк (СБП): 2200 7020 8382 3521 (Тбанк)

❗️ ВАЖНО: В комментарии к платежу укажи свой Telegram ID: {user_id}

После оплаты нажми кнопку "Я оплатил(а)" и пришли скриншот
"""

# ========== ФУНКЦИИ АДМИНА (ОБРАБОТЧИКИ СООБЩЕНИЙ) ==========
async def handle_proxy_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.user_data.get('awaiting_proxy'):
        return
    server = context.user_data.get('target_server')
    if not server:
        await update.message.reply_text("❌ Сначала выбери сервер в админ-панели")
        context.user_data['awaiting_proxy'] = False
        return
    proxies_text = update.message.text.strip()
    new_proxies = [p.strip() for p in proxies_text.split('\n') if p.strip()]
    if server not in proxies_pool:
        proxies_pool[server] = []
    added = []
    for proxy in new_proxies:
        if proxy not in proxies_pool[server]:
            proxies_pool[server].append(proxy)
            added.append(proxy)
    save_proxies(proxies_pool)
    await update.message.reply_text(f"✅ Добавлено {len(added)} прокси на сервер {server}\n\n📦 Теперь в наличии: {len(proxies_pool[server])} шт.")
    context.user_data['awaiting_proxy'] = False
    context.user_data['target_server'] = None

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.user_data.get('broadcast_mode'):
        return
    message_text = update.message.text
    if message_text == '/cancel':
        context.user_data['broadcast_mode'] = False
        await update.message.reply_text("❌ Рассылка отменена")
        return
    users = set()
    for order in orders.values():
        if order.get('user_id'):
            users.add(order['user_id'])
    await update.message.reply_text(f"📨 Начинаю рассылку {len(users)} пользователям...")
    success = 0
    fail = 0
    for user_id in users:
        try:
            await context.bot.send_message(user_id, f"📢 **Анонс от администрации:**\n\n{message_text}", parse_mode='Markdown')
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    context.user_data['broadcast_mode'] = False
    await update.message.reply_text(f"✅ Рассылка завершена!\n📨 Доставлено: {success}\n❌ Не доставлено: {fail}")

async def handle_payment_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.user_data.get('awaiting_payment_details'):
        return
    new_details = update.message.text
    if new_details == '/cancel':
        context.user_data['awaiting_payment_details'] = False
        await update.message.reply_text("❌ Изменение отменено")
        return
    settings['payment_details'] = new_details
    save_settings(settings)
    context.user_data['awaiting_payment_details'] = False
    await update.message.reply_text(f"✅ Реквизиты успешно обновлены!\n\nНовые реквизиты:\n{new_details}")

async def handle_price_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    plan_id = context.user_data.get('editing_price')
    if not plan_id:
        return
    try:
        new_price = int(update.message.text)
        SUBSCRIPTION_PLANS[plan_id]['price'] = new_price
        context.user_data['editing_price'] = None
        await update.message.reply_text(f"✅ Цена для тарифа {SUBSCRIPTION_PLANS[plan_id]['name']} изменена на {new_price}₽")
    except ValueError:
        await update.message.reply_text("❌ Ошибка! Отправь число (например: 199)")

async def handle_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Нет доступа")
        return
    if context.user_data.get('awaiting_proxy'):
        await handle_proxy_input(update, context)
    elif context.user_data.get('broadcast_mode'):
        await handle_broadcast(update, context)
    elif context.user_data.get('awaiting_payment_details'):
        await handle_payment_details(update, context)
    elif context.user_data.get('editing_price'):
        await handle_price_change(update, context)
    else:
        await update.message.reply_text("❌ Неизвестная команда. Используй кнопки меню.")

# ========== ПРОВЕРКА ИСТЕКШИХ ПОДПИСОК ==========
async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    expired_orders = []
    for order_id, order in orders.items():
        if order.get('status') == 'completed' and order.get('expires_at'):
            expires_at = datetime.fromisoformat(order['expires_at'])
            if now > expires_at:
                expired_orders.append(order_id)
                order['status'] = 'expired'
                try:
                    await context.bot.send_message(order['user_id'], f"⏰ Срок действия подписки на тариф '{order['plan']}' истёк!\nЧтобы продлить, нажми /start и выбери 'Купить прокси'")
                except:
                    pass
    if expired_orders:
        save_orders(orders)
        logger.info(f"Отключено {len(expired_orders)} истёкших подписок")
        await context.bot.send_message(ADMIN_ID, f"📊 Отчёт: {len(expired_orders)} подписок истекли и были отключены")

def start_expiry_checker():
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(check_expired_subscriptions, interval=3600, first=10)

# ========== АДМИН-ПАНЕЛЬ ==========
def get_stats():
    total_orders = len(orders)
    active_orders = sum(1 for o in orders.values() if o.get('status') == 'completed')
    expired_orders = sum(1 for o in orders.values() if o.get('status') == 'expired')
    total_revenue = sum(o.get('price', 0) for o in orders.values() if o.get('status') == 'completed')
    proxies_left = sum(len(p) for p in proxies_pool.values())
    return {'total_orders': total_orders, 'active_orders': active_orders, 'expired_orders': expired_orders, 'total_revenue': total_revenue, 'proxies_left': proxies_left}

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Доступ запрещён")
        return
    stats = get_stats()
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("➕ Добавить прокси", callback_data='admin_add_proxy')],
        [InlineKeyboardButton("📋 Список прокси", callback_data='admin_list_proxies')],
        [InlineKeyboardButton("👥 Все заказы", callback_data='admin_all_orders')],
        [InlineKeyboardButton("📢 Рассылка", callback_data='admin_broadcast')],
        [InlineKeyboardButton("⚙️ Настройки", callback_data='admin_settings')],
        [InlineKeyboardButton("💾 Резервное копирование", callback_data='admin_backup')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"🔧 **Админ-панель**\n\n📈 Всего заказов: {stats['total_orders']}\n✅ Активных: {stats['active_orders']}\n⏰ Истекло: {stats['expired_orders']}\n💰 Выручка: {stats['total_revenue']}₽\n📦 Осталось прокси: {stats['proxies_left']}\n"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        await update.callback_query.answer("⛔️ Нет доступа", show_alert=True)
        return
    query = update.callback_query
    await query.answer()
    stats = get_stats()
    plan_stats = defaultdict(int)
    for order in orders.values():
        if order.get('status') == 'completed':
            plan_stats[order.get('plan', 'unknown')] += 1
    text = f"📊 **Детальная статистика**\n\n📦 Всего заказов: {stats['total_orders']}\n✅ Активных: {stats['active_orders']}\n⏰ Истекло: {stats['expired_orders']}\n💰 Выручка: {stats['total_revenue']}₽\n📦 Прокси в наличии: {stats['proxies_left']}\n\n📈 **По тарифам:**\n"
    for plan, count in plan_stats.items():
        text += f"• {plan}: {count} шт.\n"
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_add_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Server1 (IPv4)", callback_data='addproxy_server1')],
        [InlineKeyboardButton("👥 Server2 (IPv4 3 users)", callback_data='addproxy_server2')],
        [InlineKeyboardButton("🌐 Server3 (IPv6)", callback_data='addproxy_server3')],
        [InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]
    ]
    await query.edit_message_text("➕ **Добавление прокси**\n\nВыбери сервер, затем отправь прокси в формате:\n`ip:port` или `ip:port:login:password`\n\nМожно отправить несколько, каждый с новой строки", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    context.user_data['awaiting_proxy'] = True

async def admin_list_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    text = "📋 **Список прокси**\n\n"
    for server, proxies in proxies_pool.items():
        text += f"**{server}:** {len(proxies)} шт.\n"
        for i, proxy in enumerate(proxies[:5], 1):
            text += f"  {i}. {proxy}\n"
        if len(proxies) > 5:
            text += f"  ... и ещё {len(proxies)-5}\n"
        text += "\n"
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    if not orders:
        await query.edit_message_text("📭 Нет заказов")
        return
    text = "📋 **Все заказы:**\n\n"
    for order_id, order in list(orders.items())[-20:]:
        status_emoji = "✅" if order.get('status') == 'completed' else "⏳" if order.get('status') == 'pending' else "❌"
        text += f"{status_emoji} `{order_id}` | {order.get('plan')} | @{order.get('username', 'no')}\n"
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 **Рассылка**\n\nОтправь сообщение для рассылки всем пользователям\nДля отмены отправь /cancel", parse_mode='Markdown')
    context.user_data['broadcast_mode'] = True

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💰 Изменить реквизиты", callback_data='admin_set_payment')],
        [InlineKeyboardButton("💵 Изменить цены", callback_data='admin_set_prices')],
        [InlineKeyboardButton("◀️ Назад", callback_data='admin_panel')]
    ]
    await query.edit_message_text("⚙️ **Настройки бота**\n\n" + f"Текущие реквизиты: `{settings.get('payment_details', 'Не заданы')}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    backup_data = {'orders': orders, 'proxies': proxies_pool, 'settings': settings, 'backup_date': datetime.now().isoformat()}
    backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_file, 'w') as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)
    with open(backup_file, 'rb') as f:
        await context.bot.send_document(ADMIN_ID, f, caption="💾 Резервная копия бота")
    os.remove(backup_file)
    await query.edit_message_text("✅ Резервная копия создана и отправлена!")

async def admin_set_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💰 **Изменение реквизитов**\n\nОтправь новый текст реквизитов для оплаты.\nФормат: любой текст с картой/кошельком\n\nДля отмены отправь /cancel", parse_mode='Markdown')
    context.user_data['awaiting_payment_details'] = True

async def admin_set_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    keyboard = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        keyboard.append([InlineKeyboardButton(f"{plan['name']} - текущая цена: {plan['price']}₽", callback_data=f"price_{plan_id}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='admin_settings')])
    await query.edit_message_text("💵 **Изменение цен**\n\nВыбери тариф для изменения цены:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def price_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.from_user.id != ADMIN_ID:
        return
    query = update.callback_query
    await query.answer()
    plan_id = query.data.replace('price_', '')
    context.user_data['editing_price'] = plan_id
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    await query.edit_message_text(f"💰 Изменение цены для тарифа: **{plan['name']}**\nТекущая цена: {plan['price']}₽\n\nОтправь **новую цену** (только число, без ₽)\n\nДля отмены отправь /cancel", parse_mode='Markdown')

# ========== ФУНКЦИИ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🛒 Купить прокси", callback_data='buy')],
        [InlineKeyboardButton("ℹ️ Мои заказы", callback_data='my_subscriptions')],
        [InlineKeyboardButton("🆘 Помощь", callback_data='help')]
    ]
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🔧 Админ-панель", callback_data='admin_panel')])
    await update.message.reply_text("👋 Привет! Я бот для продажи прокси.\n\nВыбери действие:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        keyboard.append([InlineKeyboardButton(f"{plan['name']} - {plan['price']}₽ / {plan['days']} дней", callback_data=f"select_{plan_id}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back_to_main')])
    await query.edit_message_text("📋 Выбери тариф:", reply_markup=InlineKeyboardMarkup(keyboard))

async def select_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = query.data.replace('select_', '')
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        await query.edit_message_text("❌ Тариф не найден")
        return
    context.user_data['selected_plan'] = plan_id
    keyboard = [[InlineKeyboardButton("✅ Я оплатил(а)", callback_data=f"paid_{plan_id}")], [InlineKeyboardButton("◀️ Назад к тарифам", callback_data='buy')]]
    payment_text = PAYMENT_DETAILS.format(user_id=query.from_user.id)
    await query.edit_message_text(f"💰 Тариф: {plan['name']}\n💵 Цена: {plan['price']}₽\n📆 Срок: {plan['days']} дней\n\n{payment_text}", reply_markup=InlineKeyboardMarkup(keyboard))

async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        user = query.from_user
        plan_id = query.data.replace('paid_', '')
        plan = SUBSCRIPTION_PLANS.get(plan_id)
        if not plan:
            await query.edit_message_text("❌ Тариф не найден")
            return
        if not proxies_pool.get(plan['server']) or len(proxies_pool[plan['server']]) == 0:
            await query.edit_message_text("❌ К сожалению, прокси на этот сервер временно закончились.\nПожалуйста, выбери другой тариф или напиши администратору.")
            return
        order_id = f"{user.id}_{int(datetime.now().timestamp())}"
        orders[order_id] = {'user_id': user.id, 'username': user.username, 'first_name': user.first_name, 'plan': plan['name'], 'price': plan['price'], 'status': 'pending', 'server': plan['server'], 'created_at': datetime.now().isoformat()}
        save_orders(orders)
        admin_keyboard = [[InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{order_id}")], [InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{order_id}")]]
        await context.bot.send_message(ADMIN_ID, f"🆕 **Новый заказ!**\n\n👤 Пользователь: @{user.username or 'нет'} (ID: {user.id})\n📦 Тариф: {plan['name']}\n💵 Сумма: {plan['price']}₽\n🆔 Заказ: `{order_id}`\n\nПроверь оплату и подтверди:", reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode='Markdown')
        await query.edit_message_text("✅ Запрос на оплату отправлен администратору!\n\n⚠️ Не забудь прислать скриншот оплаты админу в личные сообщения.\nКак только оплата подтвердится, ты получишь прокси.")
    except Exception as e:
        logger.error(f"Ошибка в paid: {e}")
        await query.edit_message_text("❌ Произошла ошибка. Попробуй позже или напиши админу.")

async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("⛔️ У тебя нет прав администратора.")
        return
    order_id = query.data.replace('confirm_', '')
    order = orders.get(order_id)
    if not order:
        await query.edit_message_text("❌ Заказ не найден")
        return
    if order['status'] == 'completed':
        await query.edit_message_text("⚠️ Этот заказ уже был подтверждён!")
        return
    server = order['server']
    if not proxies_pool.get(server) or len(proxies_pool[server]) == 0:
        await query.edit_message_text("❌ Нет доступных прокси на этом сервере!")
        return
    proxy = proxies_pool[server].pop(0)
    save_proxies(proxies_pool)
    expires_at = datetime.now() + timedelta(days=7)
    order['status'] = 'completed'
    order['proxy'] = proxy
    order['confirmed_at'] = datetime.now().isoformat()
    order['expires_at'] = expires_at.isoformat()
    save_orders(orders)
    try:
        await context.bot.send_message(order['user_id'], f"✅ **Оплата подтверждена!**\n\n🔑 Твои прокси:\n`{proxy}`\n\n📆 Срок действия до: `{expires_at.strftime('%d.%m.%Y %H:%M')}`\n⚙️ Инструкция: просто вставь эти данные в настройки.\n\n📞 По вопросам: @gooniur", parse_mode='Markdown')
        await query.edit_message_text(f"✅ Прокси `{proxy}` отправлен пользователю @{order['username']}", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка при отправке прокси: {e}")
        await query.edit_message_text(f"❌ Ошибка при отправке: {e}")

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    order_id = query.data.replace('reject_', '')
    order = orders.get(order_id)
    if order and order['status'] == 'pending':
        order['status'] = 'rejected'
        order['rejected_at'] = datetime.now().isoformat()
        save_orders(orders)
        await context.bot.send_message(order['user_id'], "❌ К сожалению, оплата не подтверждена.\nПроверь правильность перевода или свяжись с поддержкой: @gooniur")
    await query.edit_message_text("❌ Заказ отклонён")

async def my_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_orders = [o for o in orders.values() if o['user_id'] == query.from_user.id]
    active_orders = [o for o in user_orders if o.get('status') == 'completed']
    pending_orders = [o for o in user_orders if o.get('status') == 'pending']
    if not active_orders and not pending_orders:
        await query.edit_message_text("📭 У тебя пока нет заказов.\nИспользуй 'Купить прокси' для оформления.")
        return
    text = "📋 **Твои заказы:**\n\n"
    if active_orders:
        text += "✅ **Активные:**\n"
        for order in active_orders:
            expires_at = datetime.fromisoformat(order['expires_at']) if order.get('expires_at') else None
            if expires_at:
                days_left = (expires_at - datetime.now()).days
                text += f"• {order['plan']} - осталось {days_left} дн.\n`{order.get('proxy', 'нет')}`\n"
    if pending_orders:
        text += "\n⏳ **Ожидают подтверждения:**\n"
        for order in pending_orders:
            text += f"• {order['plan']} - {order['price']}₽\n"
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back_to_main')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🆘 **Помощь**\n\n• /start - главное меню\n• После оплаты нажми 'Я оплатил(а)'\n• Обязательно укажи свой Telegram ID в комментарии к платежу\n• Скриншот отправляй @gooniur\n\n📞 Поддержка: @gooniur", parse_mode='Markdown')

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🛒 Купить прокси", callback_data='buy')],
        [InlineKeyboardButton("ℹ️ Мои заказы", callback_data='my_subscriptions')],
        [InlineKeyboardButton("🆘 Помощь", callback_data='help')]
    ]
    if query.from_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🔧 Админ-панель", callback_data='admin_panel')])
    await query.edit_message_text("👋 Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))

# ========== ОБРАБОТЧИК ADMIN CALLBACK ==========
async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == 'admin_panel':
        await admin_panel(update, context)
    elif data == 'admin_stats':
        await admin_stats(update, context)
    elif data == 'admin_add_proxy':
        await admin_add_proxy(update, context)
    elif data.startswith('addproxy_'):
        server = data.replace('addproxy_', '')
        context.user_data['target_server'] = server
        await query.edit_message_text(f"✅ Выбран сервер {server}\n\nОтправь прокси в формате:\n`ip:port` или `ip:port:login:password`\nМожно несколько, каждый с новой строки\n\nДля отмены отправь /cancel", parse_mode='Markdown')
        context.user_data['awaiting_proxy'] = True
        await query.answer()
    elif data == 'admin_list_proxies':
        await admin_list_proxies(update, context)
    elif data == 'admin_all_orders':
        await admin_all_orders(update, context)
    elif data == 'admin_broadcast':
        await admin_broadcast(update, context)
    elif data == 'admin_settings':
        await admin_settings(update, context)
    elif data == 'admin_backup':
        await admin_backup(update, context)
    elif data == 'admin_set_payment':
        await admin_set_payment(update, context)
    elif data == 'admin_set_prices':
        await admin_set_prices(update, context)
    elif data.startswith('price_'):
        await price_edit(update, context)

# ========== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ==========
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(CallbackQueryHandler(show_plans, pattern="^buy$"))
app.add_handler(CallbackQueryHandler(select_plan, pattern="^select_"))
app.add_handler(CallbackQueryHandler(paid, pattern="^paid_"))
app.add_handler(CallbackQueryHandler(confirm_payment, pattern="^confirm_"))
app.add_handler(CallbackQueryHandler(reject_payment, pattern="^reject_"))
app.add_handler(CallbackQueryHandler(my_subscriptions, pattern="^my_subscriptions$"))
app.add_handler(CallbackQueryHandler(help_handler, pattern="^help$"))
app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin|^addproxy_|^price_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_messages))

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 Бот запущен...")
    print(f"📊 Админ ID: {ADMIN_ID}")
    start_expiry_checker()
    app.run_polling()
