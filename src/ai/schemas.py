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


TRANSLATION_PROMPT = """You are a professional Russian (ru) to Belarusian (be) translator. Your goal is to accurately convey the meaning and nuances of the original Russian text while adhering to Belarusian grammar, vocabulary, and cultural sensitivities.
Produce only the Belarusian translation, without any additional explanations or commentary. Please translate the following Russian text into Belarusian:


Загаловак: {title}

Тэкст:
{content}"""


POLISH_PROMPT = """Ты — рэдактар-карэктар беларускамоўнага сайта. Выпраў і структуруй пераклад ніжэй.

ПРАВІЛЫ:
- Папраў граматычныя і стылістычныя памылкі
- Правільна напішы назвы камандаў, пілотаў і тэрміны
- Захавай сэнс арыгінала
- Зрабі тэкст натуральным для беларускага чытача
- Выкарыстоўвай нарматыўную беларускую мову
- Дзеясловы ў інфінітыве на -ць, прошлы час мужчынскага роду на -ў
- Выкарыстоўвай у/ў па правілах
- Захавай УВЁСЬ тэкст перакладу, не скарачай

Пераклад: {raw_be}

ВЫПРАЎЛЕНЫ ТЭКСТ (выключна ў фармаце ніжэй):
Загаловак: <загаловак па-беларуску>
Тэкст: <поўны выпраўлены пераклад>"""


ANALYSIS_PROMPT = """Ты — рэдактар беларускамоўнага навінавага канала пра Формулу-1.

Прааналізуй беларускі тэкст навіны ніжэй:
1. Захавай поўны тэкст перакладу ў полі summary_be (без змен)
2. Вылучы 1-3 галоўныя факты па-беларуску (кароткія сказы)
3. Вызнач танальнасць (positive/negative/neutral)
4. Ацані важнасць ад 1 (дробязь) да 5 (сенсацыя)
5. Дадай 2-5 тэгаў па-беларуску

Загаловак: {title_be}

Тэкст:
{summary_be}"""


KEY_POINTS_PROMPT = """Ты — рэдактар беларускамоўнага навінавага канала пра Формулу-1.

На аснове загалоўка і кароткага зместу навіны вылучы 1-3 галоўныя факты па-беларуску.
Кожны факт — адзін кароткі сказ.

Загаловак: {title_be}

Змест:
{summary_be}"""
