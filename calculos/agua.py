"""Compatibilidade: os cálculos agora estão em calculos.services."""

from .services import calcular_agua, calcular_consumo_agua, calcular_valor_agua

__all__ = ["calcular_agua", "calcular_consumo_agua", "calcular_valor_agua"]
