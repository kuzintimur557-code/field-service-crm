import re

POSITIVE_WORDS = (
    "спасибо", "благодарю", "отлично", "прекрасно", "супер", "здорово",
    "доволен", "довольна", "рад", "класс", "всё хорошо", "все хорошо",
    "всё отлично", "все отлично", "умница", "молодец", "порядке", "рекомендую",
)
NEGATIVE_WORDS = (
    "плохо", "ужасно", "отвратительно", "груб", "обман", "жалоба",
    "недоволен", "недовольна", "разочар", "опозд", "поздно", "дорого",
    "переплат", "некачественно", "надоело", "хам", "испортили", "сломали",
)
SALE_KEYWORDS = (
    "оплатил", "оплатили", "оплачен", "внес предоплату", "предоплата внесена",
    "договорились", "согласовал", "согласилась", "согласился", "подтвердил заказ",
    "подтвердила заказ", "заказ подтверждён", "заказ подтвержден",
    "выставил счёт", "выставил счет", "выставили счёт", "выставили счет",
    "счёт оплачен", "счет оплачен", "счёт отправлен", "счет отправлен",
    "подписали", "записали на", "записан на", "ждём монтаж", "ждем монтаж",
)
FOLLOW_UP_MARKERS = (
    "перезвон", "обещал", "обещала", "напомни", "пришл", "выслать",
    "высылаю", "подготов", "уточн", "запишем на", "записать на",
    "ждём", "ждем", "следующий шаг", "доделать", "проверить", "переслать",
    "отправить", "передзвоню", "вернусь к вам", "на связи",
)

SENTIMENT_POSITIVE = "positive"
SENTIMENT_NEUTRAL = "neutral"
SENTIMENT_NEGATIVE = "negative"

MAX_FOLLOW_UP_SENTENCES = 3
MAX_FOLLOW_UP_TEXT = 300


def _combined_text(summary, transcript, ai_summary):
    return "\n".join(
        str(part or "")
        for part in (summary, transcript, ai_summary)
        if str(part or "").strip()
    ).strip()


def _count_matches(lowered, words):
    return sum(lowered.count(word) for word in words)


def analyze_call_text(summary, transcript, ai_summary):
    text = _combined_text(summary, transcript, ai_summary)
    lowered = text.lower()

    if not text:
        return {
            "sentiment": "",
            "sale_detected": False,
            "follow_up_detected": False,
            "follow_up_text": "",
        }

    positive = _count_matches(lowered, POSITIVE_WORDS)
    negative = _count_matches(lowered, NEGATIVE_WORDS)

    if positive > negative:
        sentiment = SENTIMENT_POSITIVE
    elif negative > positive:
        sentiment = SENTIMENT_NEGATIVE
    else:
        sentiment = SENTIMENT_NEUTRAL

    sale_detected = any(word in lowered for word in SALE_KEYWORDS)

    follow_up_sentences = []
    for raw_line in re.split(r"[\n.;!?]", text):
        sentence = raw_line.strip()
        lowered_line = sentence.lower()

        if not sentence or not any(
            marker in lowered_line for marker in FOLLOW_UP_MARKERS
        ):
            continue

        if sentence not in follow_up_sentences:
            follow_up_sentences.append(sentence)

        if len(follow_up_sentences) >= MAX_FOLLOW_UP_SENTENCES:
            break

    follow_up_text = " · ".join(follow_up_sentences)[:MAX_FOLLOW_UP_TEXT]

    return {
        "sentiment": sentiment,
        "sale_detected": sale_detected,
        "follow_up_detected": bool(follow_up_sentences),
        "follow_up_text": follow_up_text,
    }
