"""Small, deterministic multilingual intent engine built on spaCy Matcher.

This intentionally uses spaCy's blank multilingual tokenizer only. There is no
statistical pipeline, downloaded model, LLM call, or generated business data.
All prices and service names are read from the database before replying.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import spacy
from spacy.matcher import Matcher


@dataclass
class ChatResult:
    intent: str
    reply: str
    service_id: int | None = None
    next_action: str | None = None


INTENT_PHRASES: dict[str, tuple[str, ...]] = {
    "greeting": (
        "hi",
        "hello",
        "hey",
        "namaste",
        "नमस्कार",
        "नमस्ते",
        "हॅलो",
        "हाय",
    ),
    "service_search": (
        "services",
        "service list",
        "what do you offer",
        "what services do you have",
        "treatments",
        "available services",
        "काय काय सेवा",
        "कोणत्या सेवा",
        "सेवा दाखवा",
        "काय करता",
    ),
    "price_inquiry": (
        "price",
        "prices",
        "cost",
        "rate",
        "charges",
        "how much",
        "किंमत",
        "किती",
        "कितीला",
        "दर काय",
        "रेट काय",
        "काय रेट",
    ),
    "booking_request": (
        "book",
        "booking",
        "appointment",
        "schedule",
        "reserve a slot",
        "book a slot",
        "want a slot",
        "बुकिंग",
        "अपॉइंटमेंट",
        "वेळ ठरवायची",
        "बुक करायचा",
        "बुक करायची",
    ),
    "location": (
        "where are you",
        "where is the salon",
        "location",
        "address",
        "directions",
        "map",
        "कुठे आहे",
        "पत्ता",
        "लोकेशन",
        "दिशा",
    ),
    "timings": (
        "opening hours",
        "business hours",
        "working hours",
        "what time are you open",
        "when are you open",
        "timing",
        "timings",
        "वेळ",
        "कधी उघडता",
        "कधी बंद",
    ),
    "home_service": (
        "home service",
        "home visit",
        "at home",
        "visit my home",
        "घरी सेवा",
        "घरपोच सेवा",
        "घरी येता",
    ),
    "bridal": (
        "bridal",
        "bride",
        "wedding makeup",
        "bridal makeup",
        "लग्न मेकअप",
        "नवरी",
        "वधू",
    ),
    "contact": (
        "phone number",
        "phone",
        "call you",
        "whatsapp",
        "contact",
        "number",
        "फोन नंबर",
        "संपर्क",
        "व्हॉट्सअॅप",
    ),
}

INTENT_PRIORITY = {
    "booking_request": 9,
    "price_inquiry": 8,
    "location": 7,
    "timings": 7,
    "home_service": 7,
    "contact": 6,
    "bridal": 5,
    "service_search": 5,
    "greeting": 2,
}

SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "classic bridal makeup": ("classic bridal", "bridal makeup", "bridal package"),
    "hd / airbrush bridal makeup": ("hd makeup", "airbrush makeup", "hd airbrush"),
    "cleanup": ("clean up",),
    "fruit / gold facial": ("fruit facial", "gold facial", "facial"),
    "advanced hydra facial": ("hydra", "hydra facial"),
    "hair spa": ("hair spa",),
    "smoothening / keratin": ("smoothening", "hair smoothening", "keratin"),
    "hair styling": ("hairstyling", "hair style"),
    "manicure": ("manicure",),
    "pedicure": ("pedicure",),
    "nail extensions": ("artificial nails", "nail extension"),
    "waxing + threading package": ("waxing", "threading", "waxing threading"),
    "saree draping": ("saree", "sari draping"),
    "event makeup": ("party makeup", "function makeup"),
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
    text = re.sub(r"[?!.。,،;:()\[\]{}<>/\\|]+", " ", text)
    return re.sub(r"\s+", " ", text)


def _pattern(nlp: Any, phrase: str) -> list[dict[str, Any]]:
    return [{"LOWER": token.text.lower()} for token in nlp.make_doc(_normalize(phrase))]


def _add_phrases(matcher: Matcher, nlp: Any, name: str, phrases: tuple[str, ...]) -> None:
    patterns = [_pattern(nlp, phrase) for phrase in phrases if phrase.strip()]
    if patterns:
        matcher.add(name, patterns)


class MitalliMatcher:
    def __init__(self, services: list[dict[str, Any]]):
        self.nlp = spacy.blank("xx")
        self.intent_matcher = Matcher(self.nlp.vocab)
        for intent, phrases in INTENT_PHRASES.items():
            _add_phrases(self.intent_matcher, self.nlp, f"INTENT_{intent}", phrases)

        # Catch inflected English words without a statistical model.
        self.intent_matcher.add("INTENT_booking_request", [
            [{"LOWER": {"REGEX": r"book(?:ing|ed)?|schedul(?:e|ing)|reserv(?:e|ation)?"}}],
        ])
        self.intent_matcher.add("INTENT_price_inquiry", [
            [{"LOWER": {"REGEX": r"price|cost|rate|charg(?:e|es)?"}}],
        ])

        self.service_matcher = Matcher(self.nlp.vocab)
        self.service_by_rule: dict[str, dict[str, Any]] = {}
        for service in services:
            canonical = str(service["name"]).lower()
            aliases = set(SERVICE_ALIASES.get(canonical, ()))
            aliases.add(canonical)
            rule_name = f"SERVICE_{service['id']}"
            self.service_by_rule[rule_name] = service
            self.service_matcher.add(
                rule_name,
                [_pattern(self.nlp, alias) for alias in sorted(aliases, key=len, reverse=True)],
            )

    def detect_service(self, doc: Any) -> dict[str, Any] | None:
        matches = self.service_matcher(doc)
        if not matches:
            return None
        match_id, start, end = max(matches, key=lambda item: (item[2] - item[1], -item[1]))
        return self.service_by_rule[self.nlp.vocab.strings[match_id]]

    def detect(self, text: str) -> ChatResult:
        normalized = _normalize(text)
        doc = self.nlp(normalized)
        scores: dict[str, int] = {}
        for match_id, start, end in self.intent_matcher(doc):
            name = self.nlp.vocab.strings[match_id].removeprefix("INTENT_")
            span_score = max(1, end - start) * INTENT_PRIORITY.get(name, 1)
            scores[name] = scores.get(name, 0) + span_score

        service = self.detect_service(doc)
        intent = max(scores, key=scores.get) if scores else "fallback"

        # A service plus an explicit price/booking word is more useful than
        # the generic service intent. The score rules above handle most cases;
        # these tie-breakers make mixed Marathi-English phrases predictable.
        if service and scores.get("booking_request", 0) >= 9:
            intent = "booking_request"
        elif service and scores.get("price_inquiry", 0) >= 8:
            intent = "price_inquiry"
        elif service and not scores:
            intent = "service_search"

        return self._reply(intent, service, normalized)

    def _reply(
        self,
        intent: str,
        service: dict[str, Any] | None,
        normalized: str,
    ) -> ChatResult:
        if intent == "greeting":
            return ChatResult(
                intent,
                "नमस्कार! Mitalli Bridal World मध्ये स्वागत आहे. Services, prices किंवा appointment बद्दल विचारा.",
            )
        if intent == "service_search":
            return ChatResult(
                intent,
                "आमच्या services मध्ये bridal makeup, facial, hair care, nails, waxing आणि event styling आहेत. तुम्हाला कोणती सेवा हवी आहे?",
                next_action="services",
            )
        if intent == "price_inquiry":
            if service:
                price = self._price(service)
                return ChatResult(
                    intent,
                    f"{service['name']} ची listed price {price} आहे. Final quote तुमच्या look आणि consultation नंतर confirm केला जाईल.",
                    service_id=service["id"],
                    next_action="booking",
                )
            return ChatResult(
                intent,
                "काही popular starting prices: Classic Bridal Makeup ₹12,000 पासून, HD/Airbrush ₹18,000 पासून आणि Cleanup ₹500 पासून. Exact quote साठी service निवडा.",
                next_action="services",
            )
        if intent == "booking_request":
            detail = f" {service['name']} साठी" if service else ""
            return ChatResult(
                intent,
                f"{detail} appointment request घेऊ शकते. खाली Book appointment form भरा; request मिळाल्यावर आमची team slot confirm करेल.",
                service_id=service["id"] if service else None,
                next_action="booking",
            )
        if intent == "location":
            return ChatResult(
                intent,
                "Mitalli Bridal World, Near Mantri Bank, Nashik Road, Sangamner, Maharashtra 422605. Directions साठी Contact section मधील map button वापरा.",
                next_action="location",
            )
        if intent == "timings":
            return ChatResult(
                intent,
                "सध्या listed hours Monday–Saturday, 9:30 AM–6:30 PM आहेत. Sunday closed. Appointment आधी call करून slot confirm करा.",
                next_action="contact",
            )
        if intent == "home_service":
            return ChatResult(
                intent,
                "Home service availability service आणि date नुसार बदलू शकते. तुमची requirement पाठवा किंवा WhatsApp वर team शी बोलूया.",
                next_action="contact",
            )
        if intent == "bridal":
            return ChatResult(
                intent,
                "Bridal makeup साठी Classic आणि HD/Airbrush options उपलब्ध आहेत. तुमच्या wedding date आणि preferred look सह appointment request पाठवा.",
                service_id=service["id"] if service else None,
                next_action="booking",
            )
        if intent == "contact":
            return ChatResult(
                intent,
                "Call: 07383099084. WhatsApp वर service, date आणि time पाठवल्यास team लवकर reply करेल.",
                next_action="contact",
            )
        return ChatResult(
            "fallback",
            "माफ करा, मला ते पूर्णपणे समजले नाही. तुम्ही services, prices, bridal makeup, appointment, location किंवा timings बद्दल विचारू शकता.",
            next_action="suggestions",
        )

    @staticmethod
    def _price(service: dict[str, Any]) -> str:
        if service.get("price") is None or service.get("price_type") == "on_request":
            return "on request"
        suffix = " पासून" if service.get("price_type") == "starting_from" else ""
        return f"₹{int(service['price']):,}{suffix}"


def build_matcher(services: list[dict[str, Any]]) -> MitalliMatcher:
    return MitalliMatcher(services)