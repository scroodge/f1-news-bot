"""
Structured output schema for news analysis.

Three-stage pipeline:
1. TranslateGemma 12B — pure RU→BE translation
2. Sonnet — polish raw translation, produce clean title + summary
3. Haiku/Sonnet — analyze BE text for key points, tags, sentiment, importance
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NewsAnalysis(BaseModel):
    """Belarusian-language analysis of one news item"""

    title_be: str = Field(description="Загаловак навіны па-беларуску, кароткі і дакладны")
    summary_be: str = Field(
        description="Поўны пераклад тэксту навіны па-беларуску, без скарачэнняў"
    )
    key_points_be: list[str] = Field(
        default_factory=list,
        description="1-3 галоўныя факты навіны па-беларуску, кожны адным кароткім сказам",
    )
    sentiment: Literal["positive", "negative", "neutral"] = Field(
        default="neutral", description="Танальнасць навіны"
    )
    importance_level: int = Field(
        default=1, description="Важнасць навіны ад 1 (дробязь) да 5 (сенсацыя)"
    )
    tags_be: list[str] = Field(
        default_factory=list,
        description="2-5 тэгаў па-беларуску, напрыклад: гонка, ферстапен, кваліфікацыя",
    )

    @field_validator("importance_level", mode="before")
    @classmethod
    def _clamp_importance(cls, value):
        try:
            return max(1, min(5, int(value)))
        except (TypeError, ValueError):
            return 1

    @field_validator("key_points_be")
    @classmethod
    def _limit_key_points(cls, value: list[str]) -> list[str]:
        return value[:3]

    @field_validator("tags_be")
    @classmethod
    def _limit_tags(cls, value: list[str]) -> list[str]:
        return value[:5]


class KeyPointsAnalysis(BaseModel):
    """Belarusian key points extracted from already-translated content"""

    key_points_be: list[str] = Field(
        default_factory=list,
        description="1-3 галоўныя факты па-беларуску, кожны адным кароткім сказам",
    )


LANG_LABELS = {"ru": "з рускай (ru)", "en": "з англійскай (en)", "be": "з беларускай (be)"}

TRANSLATION_PROMPT = """Ты — прафесійны перакладчык {source_lang} на беларускую (be) мову.

Перакладзі наступны тэкст на беларускую мову. ВЯРНІ ТОЛЬКІ ПЕРАКЛАД, без тлумачэнняў.

ВАЖНА:
- Гэта павінна быць БЕЛАРУСКАЯ мова (be), а НЕ ўкраінская (uk)
- Захавай поўную даўжыню тэксту — нічога не скарачай
- Перакладзі ЎВЁСЬ тэкст, кожны абзац

Загаловак: {title}

Тэкст:
{content}"""

SUMMARY_PROMPT = """Напішы кароткі пераказ (2-3 сказы) гэтага беларускага тэксту навіны. Толькі факты, без каментарыяў.

Тэкст:
{content}"""

ANALYSIS_PROMPT_TG12B = """Ты — рэдактар беларускамоўнага навінавага канала пра Формулу-1.

Прааналізуй беларускі тэкст навіны ніжэй і вярні JSON з полямі:
- key_points_be: 1-3 галоўныя факты, кожны адным кароткім сказам
- tags_be: 2-5 тэгаў
- sentiment: positive/negative/neutral
- importance_level: ад 1 да 5

Загаловак: {title}

Тэкст:
{content}"""

ANALYSIS_PROMPT = """Ты — рэдактар беларускамоўнага навінавага канала пра Формулу-1.

Прааналізуй беларускі тэкст навіны ніжэй:
1. Вылучы 1-3 галоўныя факты па-беларуску
2. Вызнач танальнасць (positive/negative/neutral)
3. Ацані важнасць ад 1 (дробязь) да 5 (сенсацыя)
4. Дадай 2-5 тэгаў па-беларуску

Загаловак: {title_be}

Тэкст:
{summary_be}"""


EN_TRANSLATE_PROMPT = """Ты — прафесійны перакладчык з англійскай (en) на беларускую (be) мову.

Перакладзі гэты тэкст на беларускую мову. Захавай поўную даўжыню, кожны абзац, нічога не скарачай.

Фармат:
Загаловак: <перакладзены загаловак>
Тэкст: <поўны пераклад>

Арыгінал:
{title}

{content}"""

KEY_POINTS_PROMPT = """Ты — рэдактар беларускамоўнага навінавага канала пра Формулу-1.

На аснове загалоўка і кароткага зместу навіны вылучы 1-3 галоўныя факты па-беларуску.
Кожны факт — адзін кароткі сказ.

Загаловак: {title_be}

Змест:
{summary_be}"""

POLISH_PROMPT = """Ты — рэдактар-карэктар беларускамоўнага сайта. Выпраў і структуруй пераклад ніжэй.

ПРАВІЛЫ:
- Папраў граматычныя і стылістычныя памылкі
- Правільна напішы назвы камандаў, пілотаў і тэрміны
- Захавай сэнс арыгінала
- Зрабі тэкст натуральным для беларускага чытача
- Выкарыстоўвай нарматыўную беларускую мову
- Дзеясловы ў інфінітыве на -ць, прошлы час мужчынскага роду на -ў
- Выкарыстоўвай у/ў па правілах

КРЫТЫЧНА ВАЖНА:
- Захавай УВЁСЬ тэкст перакладу, нічога не скарачай
- Кожны абзац арыгінала павінен быць у выніку
- Гэта ПОЎНЫ пераклад, а не кароткае рэзюмэ

Пераклад: {raw_be}

ВЫПРАЎЛЕНЫ ТЭКСТ (выключна ў фармаце ніжэй):
Загаловак: <загаловак па-беларуску>
Тэкст: <поўны выпраўлены пераклад>"""
