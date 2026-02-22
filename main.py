# KnightsOfNear_engine.py
# Round-table access ledger and KOK NFT registry. Forged at the boundary of NEAR and EVM.
# Use at your own risk. Not audited.

from __future__ import annotations

import hashlib
import json
import secrets
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

# ---------------------------------------------------------------------------
# Deployed roles (EVM mainnet–style; do not reuse elsewhere)
# ---------------------------------------------------------------------------

GOVERNANCE_ROUND = "0xe7f2a4c9b1d8e3f6a0c5b2d9e4f7a1c6b3d0e8f1"
TABLE_TREASURY = "0x9a3d6f1c8e4b7a0d2f5e8c1b4a7d0e3f6c9b2a5d8"
SEAT_REGISTRAR = "0x1b5e9c3a7d0f4e8b2c6a9d3f7b0e5c1a8d4f2e6b0"
KOK_VAULT = "0x4c8a2f6e0b9d3a7c1e5f8b2d6a0c4e9f3b7d1a8c2"
BRIDGE_RELAY = "0xd2f7a1e6c0b9d4e8a3f5c1b7d0e4a9f2c6b3d5e1"
ROUND_TABLE_CORE = "0x6b0e4a8d2f7c1b5e9a3d6f0c4b8e2a7d1f5c9b0a4"
KON_TOKEN_HUB = "0xa8d1f5c9e3b7a0d4e8c2f6b9a1d5e0c3f7a4b8d2e"
MERLIN_GATE = "0x3f7b2e6a9d1c5f0e8b4a7d2f6c9e1b5a0d3f8c2b6"
LANCELOT_GATE = "0x0e5a9d3f7c2b6e1a4d8f0c5b9e3a7d2f6c1b4e0a8"
GAWAIN_GATE = "0xb9e2c6a0d4f8b1e5c9a3d7f2b6e0c4a8d1f5b3c7"
DEFAULT_FEE_RECIPIENT = "0x7c4d0f3a8e2b6c9d1f5a0e4b8c2d7f3a6e1b9c5d0"
BURN_ADDRESS = "0x000000000000000000000000000000000000dEaD"

# ---------------------------------------------------------------------------
# Constants (EVM-aligned)
# ---------------------------------------------------------------------------

KON_DECIMALS = 18
KON_SCALE = 10**18
KON_INITIAL_SUPPLY = 1_000_000_000 * KON_SCALE
KON_MAX_SUPPLY = 2_000_000_000 * KON_SCALE
ROUND_TABLE_SEATS = 150
KOK_COLLECTION_SIZE = 16
KON_BASIS_POINTS = 10_000
KON_MAX_FEE_BASIS = 250
KON_MIN_STAKE_FOR_SEAT = 10_000 * KON_SCALE
TABLE_ENTRY_FEE_WEI = 100_000_000_000_000
MAX_CLAIM_PER_TX = 50
DOMAIN_SEPARATOR_SALT = "0x8f4a2c6e1b9d0f3a7c5e8b2d6f1a4c9e0b3d7f2"
KOK_NAMESPACE = hashlib.sha256(b"KnightsOfNear.KOK_COLLECTION").hexdigest()
ROUND_TABLE_NAMESPACE = hashlib.sha256(b"KnightsOfNear.ROUND_TABLE_ACCESS").hexdigest()
EIP712_VERSION = "1"

# ---------------------------------------------------------------------------
# Custom errors (unique to this contract)
# ---------------------------------------------------------------------------


class KnightsOfNearError(Exception):
    """Base for KnightsOfNear engine."""

    pass


class TableGuardDenied(KnightsOfNearError):
    pass


class SeatAlreadyClaimed(KnightsOfNearError):
    pass


class NotAKnight(KnightsOfNearError):
    pass


class InsufficientStake(KnightsOfNearError):
    pass


class RoundTableFull(KnightsOfNearError):
    pass


class ZeroAddress(KnightsOfNearError):
    pass


class ZeroAmount(KnightsOfNearError):
    pass


class ExceedsBalance(KnightsOfNearError):
    pass


class ExceedsAllowance(KnightsOfNearError):
    pass


class FeeBasisTooHigh(KnightsOfNearError):
    pass


class KOKIndexOutOfRange(KnightsOfNearError):
    pass


class KOKAlreadyMinted(KnightsOfNearError):
    pass


class NotKOKOwner(KnightsOfNearError):
    pass


class NotGovernance(KnightsOfNearError):
    pass


class NotRegistrar(KnightsOfNearError):
    pass


class TableNotUnlocked(KnightsOfNearError):
    pass


class ClaimBatchTooLarge(KnightsOfNearError):
    pass


class InvalidSeatId(KnightsOfNearError):
    pass


class TransferToZero(KnightsOfNearError):
    pass


class MintExceedsCap(KnightsOfNearError):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SeatStatus(Enum):
    VACANT = 0
    CLAIMED = 1
    FROZEN = 2


class KOKRarity(Enum):
    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    EPIC = 3
    LEGENDARY = 4


# ---------------------------------------------------------------------------
# Events (log-style structures)
# ---------------------------------------------------------------------------


@dataclass
class EventTransfer:
    from_addr: str
    to_addr: str
    amount: int


@dataclass
class EventSeatClaimed:
    seat_id: int
    knight: str
    stake_amount: int


@dataclass
class EventKOKMinted:
    token_id: int
    to_addr: str
    rarity: KOKRarity


@dataclass
class EventTableUnlocked:
    unlocked_by: str
    block_ts: int


# ---------------------------------------------------------------------------
# Round table seat
# ---------------------------------------------------------------------------


@dataclass
class RoundTableSeat:
    seat_id: int
    occupant: str
    stake_amount: int
    claimed_at_block: int
    status: SeatStatus


# ---------------------------------------------------------------------------
# KOK NFT metadata (16 high-profile knights)
# ---------------------------------------------------------------------------

KOK_METADATA: List[Dict[str, Any]] = [
    {
        "token_id": 0,
        "name": "Arthur of Near",
        "description": "Sovereign of the Round Table. One blade to bind them.",
        "rarity": KOKRarity.LEGENDARY,
        "attributes": [{"trait_type": "Title", "value": "High King"}, {"trait_type": "Power", "value": 98}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Arthur_0").hexdigest()[:64],
    },
    {
        "token_id": 1,
        "name": "Merlin the Seer",
        "description": "Oracle of NEAR. Sees across chains.",
        "rarity": KOKRarity.LEGENDARY,
        "attributes": [{"trait_type": "Title", "value": "Prophet"}, {"trait_type": "Power", "value": 95}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Merlin_1").hexdigest()[:64],
