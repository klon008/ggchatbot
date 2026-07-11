"""Склонения и форматирование для валюты «принцессы»."""
from __future__ import annotations


def pluralize_princess(count: int) -> str:
    if 11 <= count % 100 <= 14:
        return "принцесс"
    last_digit = count % 10
    if last_digit == 1:
        return "принцесса"
    if 2 <= last_digit <= 4:
        return "принцессы"
    return "принцесс"
