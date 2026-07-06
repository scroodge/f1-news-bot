"""
Structured output schema for news analysis.

One LLM call produces the complete Belarusian-language analysis of a news
item: translated/rewritten title and summary, key points, tags, sentiment,
and importance. Both backends (Ollama json_schema and Claude structured
outputs) validate against this same model.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NewsAnalysis(BaseModel):
    """Belarusian-language analysis of one news item"""

    title_be: str = Field(description="Загаловак навіны па-беларуску, кароткі і дакладны")
    summary_be: str = Field(
        description="Кароткі пераказ навіны па-беларуску, 2-3 сказы, максімум 400 знакаў"
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


ANALYSIS_PROMPT = """Ты — рэдактар беларускамоўнага навінавага канала пра Формулу-1.

Прааналізуй навіну ніжэй і падрыхтуй яе для публікацыі ПА-БЕЛАРУСКУ:
1. Перакладзі загаловак на беларускую мову (дакладна перадай імёны піл ётаў і каманд: Ферстапен, Хэмілтан, Леклер, Норыс, Пʼястры, Расэл, Феррары, Мэрсэдэс, Рэд Бул, Макларэн).
2. Напішы кароткі пераказ (2-3 сказы) па-беларуску.
3. Вылучы 1-3 галоўныя факты.
4. Вызнач танальнасць (positive/negative/neutral) і важнасць (1-5).
5. Дадай 2-5 тэгаў па-беларуску.

Загаловак: {title}

Тэкст навіны:
{content}"""
