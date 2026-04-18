"""
Мотивационные сообщения с картинками
Используем Unsplash Source (бесплатно, без API ключа)
"""
import random

# Unsplash Source URLs — рандомные по теме, 800x600
IMAGES = {
    "morning": [
        "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1497032628192-86f99bcd76bc?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=800&h=600&fit=crop",
    ],
    "done": [
        "https://images.unsplash.com/photo-1552508744-1696d4464960?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1533227268428-f9ed0900fb3b?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&h=600&fit=crop",
    ],
    "streak": [
        "https://images.unsplash.com/photo-1526506118085-60ce8714f8c5?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&h=600&fit=crop",
    ],
    "evening": [
        "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?w=800&h=600&fit=crop",
    ],
    "day_complete": [
        "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=800&h=600&fit=crop",
    ],
    "nudge": [
        "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=800&h=600&fit=crop",
        "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=800&h=600&fit=crop",
    ],
}

MORNING_QUOTES = [
    "Путь к 1М/мес начинается с этих 4 часов.",
    "Каждый час сегодня — инвестиция в свободу.",
    "Долги не закроют себя. Клиенты не придут сами. Ты — двигатель.",
    "4 часа фокуса = больше, чем 8 часов суеты.",
    "Свобода от долгов. Турция. Ленка счастлива. Начнём?",
    "Сегодня ты становишься тем, кем хотел быть вчера.",
]

DONE_QUOTES = [
    "Готово. Каждая закрытая задача — шаг к свободе. 🔥",
    "Так держать. Ты работаешь на себя, не на кого-то.",
    "Выполнено. Momentum — самая мощная сила.",
    "Закрыто. Ещё чуть-чуть и 4 часа в кармане.",
]

EVENING_GOOD = [
    "Отличный день. Ты не просто работал — ты строил.",
    "4 часа в банке. Каждый такой день приближает 1М/мес.",
    "Молодец. Отдохни, завтра снова в бой.",
]

EVENING_BAD = [
    "Не каждый день — победа. Но завтра — новый шанс.",
    "Ничего, отдохнул — значит готов к завтрашнему рывку.",
]


def get_image(category):
    imgs = IMAGES.get(category, IMAGES["morning"])
    return random.choice(imgs)

def get_morning_quote():
    return random.choice(MORNING_QUOTES)

def get_done_quote():
    return random.choice(DONE_QUOTES)

def get_evening_quote(good=True):
    return random.choice(EVENING_GOOD if good else EVENING_BAD)
