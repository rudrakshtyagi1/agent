"""Exact symptom signatures; groups indicate similarity, not shared causality."""
import hashlib
import json


def fingerprint(category, subtype, component):
    return hashlib.sha256(json.dumps([category, subtype, component], separators=(',', ':')).encode()).hexdigest()[:24]
