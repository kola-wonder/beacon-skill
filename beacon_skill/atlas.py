"""Atlas — virtual geography, city distribution, and AI-to-AI calibration metrics.

Beacon 2.5: Agents populate virtual cities based on capabilities, specializations,
and network density. Cities emerge from clustering — urban hubs for popular skills,
rural digital homesteads for niche specialists.

Calibration metrics measure AI-to-AI interaction quality: response coherence,
latency, trust score, and domain overlap. Two agents with high calibration
are "neighbors" even if physically on different continents.

Architecture:
    - Cities are emergent clusters, not pre-defined
    - Population density = agents per capability domain
    - Property = an agent's registered "address" in a city
    - Calibration = scored quality of pairwise agent interactions
    - Districts = sub-regions within a city (specializations)
"""

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .storage import _dir

# ── Files ──
ATLAS_FILE = "atlas.json"
CALIBRATIONS_FILE = "calibrations.jsonl"
PROPERTIES_FILE = "properties.json"
VALUATIONS_FILE = "valuations.jsonl"
MARKET_HISTORY_FILE = "market_history.jsonl"

# ── City Generation Seeds ──
# Cities are named procedurally from capability hashes.
# These are the "founding" cities — canonical names for common domains.
FOUNDING_CITIES = {
    "coding":      {"name": "Compiler Heights",   "region": "Silicon Basin",  "type": "metropolis"},
    "creative":    {"name": "Muse Hollow",        "region": "Artisan Coast",  "type": "city"},
    "research":    {"name": "Archive Spire",       "region": "Scholar Wastes", "type": "city"},
    "devops":      {"name": "Pipeline Junction",   "region": "Silicon Basin",  "type": "town"},
    "security":    {"name": "Bastion Keep",        "region": "Iron Frontier",  "type": "town"},
    "data":        {"name": "Lakeshore Analytics",  "region": "Silicon Basin",  "type": "city"},
    "design":      {"name": "Palette Row",         "region": "Artisan Coast",  "type": "town"},
    "api":         {"name": "Gateway Commons",     "region": "Silicon Basin",  "type": "town"},
    "blockchain":  {"name": "Ledger Falls",        "region": "Iron Frontier",  "type": "town"},
    "ai":          {"name": "Tensor Valley",       "region": "Scholar Wastes", "type": "metropolis"},
    "gaming":      {"name": "Respawn Point",       "region": "Neon Wilds",     "type": "town"},
    "music":       {"name": "Harmony Springs",     "region": "Artisan Coast",  "type": "village"},
    "writing":     {"name": "Inkwell Crossing",    "region": "Artisan Coast",  "type": "town"},
    "hardware":    {"name": "Solder Creek",        "region": "Iron Frontier",  "type": "village"},
    "video":       {"name": "Frame Bay",           "region": "Neon Wilds",     "type": "town"},
    "education":   {"name": "Chalkboard Pines",    "region": "Scholar Wastes", "type": "village"},
    "finance":     {"name": "Margin Wharf",        "region": "Iron Frontier",  "type": "town"},
    "vintage":     {"name": "Patina Gulch",        "region": "Rust Belt",      "type": "village"},
    "networking":  {"name": "Packet Harbor",       "region": "Silicon Basin",  "type": "town"},
    "preservation": {"name": "Amber Archive",      "region": "Rust Belt",      "type": "village"},
}

# Region descriptions — flavor text for the virtual geography
REGIONS = {
    "Silicon Basin":   "Dense urban sprawl of builders and coders. High opportunity, high competition.",
    "Artisan Coast":   "Creative communities along the shores of imagination. Slower pace, deeper work.",
    "Scholar Wastes":  "Vast research plains where knowledge-seekers roam. Sparse but profound.",
    "Iron Frontier":   "Hardened security and infrastructure specialists. Trust is earned, not given.",
    "Neon Wilds":      "Entertainment and media jungle. Flashy, fast-moving, trend-driven.",
    "Rust Belt":       "Vintage computing and preservation communities. Nostalgia as a resource.",
}

# Population thresholds for city type upgrades
POPULATION_THRESHOLDS = {
    "outpost":     1,     # 1 agent — lonely homestead
    "village":     3,     # 3+ agents — small community
    "town":        10,    # 10+ agents — real town
    "city":        25,    # 25+ agents — urban center
    "metropolis":  50,    # 50+ agents — major hub
    "megalopolis": 100,   # 100+ agents — sprawling mega-city
}

# Calibration score components
CALIBRATION_WEIGHTS = {
    "domain_overlap":     0.25,   # How much capability overlap
    "trust_score":        0.25,   # From TrustManager
    "response_coherence": 0.20,   # Quality of past interactions
    "latency_score":      0.15,   # Communication speed
    "accord_bonus":       0.15,   # Bonus if accord exists
}


def _city_type_for_population(pop: int) -> str:
    """Determine city type based on population."""
    city_type = "outpost"
    for t, threshold in sorted(POPULATION_THRESHOLDS.items(), key=lambda x: x[1]):
        if pop >= threshold:
            city_type = t
    return city_type


def _generate_city_name(domain: str) -> Dict[str, str]:
    """Generate a procedural city name from a domain string."""
    # Check founding cities first
    domain_lower = domain.lower().strip()
    if domain_lower in FOUNDING_CITIES:
        return dict(FOUNDING_CITIES[domain_lower])

    # Procedural generation from hash
    h = hashlib.sha256(domain_lower.encode()).hexdigest()

    prefixes = [
        "New", "Port", "Fort", "Upper", "Lower", "Old", "East", "West",
        "North", "South", "Mount", "Lake", "River", "Crystal", "Shadow",
        "Bright", "Dark", "Silver", "Golden", "Iron", "Copper", "Pine",
    ]
    suffixes = [
        "ville", " Heights", " Springs", " Falls", " Creek", " Harbor",
        " Valley", " Ridge", " Crossing", " Junction", " Point", " Hollow",
        " Glen", " Pines", " Flats", " Bluff", " Mesa", " Gorge",
    ]

    # Use hash bytes to select prefix/suffix
    prefix_idx = int(h[:4], 16) % len(prefixes)
    suffix_idx = int(h[4:8], 16) % len(suffixes)
    region_keys = list(REGIONS.keys())
    region_idx = int(h[8:12], 16) % len(region_keys)

    name = f"{prefixes[prefix_idx]}{suffixes[suffix_idx]}"

    return {
        "name": name,
        "region": region_keys[region_idx],
        "type": "outpost",
        "generated": True,
    }


class CalibrationResult:
    """Result of an AI-to-AI calibration measurement."""

    def __init__(self, agent_a: str, agent_b: str, scores: Dict[str, float]):
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.scores = scores
        self.overall = sum(
            scores.get(k, 0.0) * w
            for k, w in CALIBRATION_WEIGHTS.items()
        )
        self.ts = int(time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_a": self.agent_a,
            "agent_b": self.agent_b,
            "scores": self.scores,
            "overall": round(self.overall, 4),
            "ts": self.ts,
        }


class AtlasManager:
    """Virtual geography — city distribution, population density, and calibration."""

    def __init__(self, data_dir: Optional[Path] = None, config: Optional[Dict] = None):
        self._dir = data_dir or _dir()
        self._config = config or {}
        self._atlas: Dict[str, Any] = {}
        self._properties: Dict[str, Any] = {}
        self._load()

    # ── Persistence ──

    def _atlas_path(self) -> Path:
        return self._dir / ATLAS_FILE

    def _properties_path(self) -> Path:
        return self._dir / PROPERTIES_FILE

    def _calibrations_path(self) -> Path:
        return self._dir / CALIBRATIONS_FILE

    def _load(self) -> None:
        for attr, path in [("_atlas", self._atlas_path()), ("_properties", self._properties_path())]:
            if path.exists():
                try:
                    setattr(self, attr, json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    setattr(self, attr, {})

        # Ensure atlas has cities section
        if "cities" not in self._atlas:
            self._atlas["cities"] = {}
        if "population" not in self._atlas:
            self._atlas["population"] = {}
        if "regions" not in self._atlas:
            self._atlas["regions"] = dict(REGIONS)

    def _save_atlas(self) -> None:
        self._atlas_path().parent.mkdir(parents=True, exist_ok=True)
        self._atlas_path().write_text(
            json.dumps(self._atlas, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _save_properties(self) -> None:
        self._properties_path().parent.mkdir(parents=True, exist_ok=True)
        self._properties_path().write_text(
            json.dumps(self._properties, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _append_calibration(self, entry: Dict[str, Any]) -> None:
        path = self._calibrations_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    # ── City Management ──

    def ensure_city(self, domain: str) -> Dict[str, Any]:
        """Ensure a city exists for a domain. Creates it if needed."""
        domain_key = domain.lower().strip()
        if domain_key in self._atlas["cities"]:
            return self._atlas["cities"][domain_key]

        city_info = _generate_city_name(domain_key)
        city_info["domain"] = domain_key
        city_info["founded_at"] = int(time.time())
        city_info["population"] = 0
        city_info["residents"] = []
        city_info["districts"] = {}

        self._atlas["cities"][domain_key] = city_info
        self._save_atlas()
        return city_info

    def get_city(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get city info by domain."""
        return self._atlas["cities"].get(domain.lower().strip())

    def all_cities(self) -> List[Dict[str, Any]]:
        """List all cities, sorted by population descending."""
        cities = list(self._atlas["cities"].values())
        cities.sort(key=lambda c: c.get("population", 0), reverse=True)
        return cities

    def cities_by_region(self, region: str) -> List[Dict[str, Any]]:
        """List cities in a specific region."""
        return [
            c for c in self._atlas["cities"].values()
            if c.get("region", "").lower() == region.lower()
        ]

    # ── Agent Registration & Properties ──

    def register_agent(self, agent_id: str, domains: List[str],
                       name: str = "", metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Register an agent in the atlas. Assigns them to cities based on domains.

        An agent can have a "primary residence" (first domain) and "offices"
        in other cities. Think of it like having a home address + work addresses.
        """
        now = int(time.time())
        primary_domain = domains[0] if domains else "general"

        # Create property record
        prop = {
            "agent_id": agent_id,
            "name": name,
            "primary_city": primary_domain,
            "cities": domains,
            "registered_at": now,
            "last_seen": now,
            "metadata": metadata or {},
        }

        # Unregister from old cities if re-registering
        old_prop = self._properties.get(agent_id)
        if old_prop:
            for old_domain in old_prop.get("cities", []):
                city = self._atlas["cities"].get(old_domain, {})
                if agent_id in city.get("residents", []):
                    city["residents"].remove(agent_id)
                    city["population"] = len(city["residents"])
                    city["type"] = _city_type_for_population(city["population"])

        # Register in new cities
        for domain in domains:
            city = self.ensure_city(domain)
            if agent_id not in city.get("residents", []):
                city["residents"].append(agent_id)
                city["population"] = len(city["residents"])
                city["type"] = _city_type_for_population(city["population"])

        self._properties[agent_id] = prop
        self._update_population_stats()
        self._save_atlas()
        self._save_properties()

        return {
            "agent_id": agent_id,
            "home": self._atlas["cities"].get(primary_domain, {}).get("name", primary_domain),
            "cities_joined": len(domains),
            "property": prop,
        }

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from all cities."""
        prop = self._properties.pop(agent_id, None)
        if not prop:
            return False

        for domain in prop.get("cities", []):
            city = self._atlas["cities"].get(domain, {})
            if agent_id in city.get("residents", []):
                city["residents"].remove(agent_id)
                city["population"] = len(city["residents"])
                city["type"] = _city_type_for_population(city["population"])

        self._update_population_stats()
        self._save_atlas()
        self._save_properties()
        return True

    def get_property(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent's property record."""
        return self._properties.get(agent_id)

    def agent_address(self, agent_id: str) -> Optional[str]:
        """Get human-readable address for an agent.

        Format: "AgentName @ CityName, Region"
        """
        prop = self._properties.get(agent_id)
        if not prop:
            return None

        primary = prop.get("primary_city", "")
        city = self._atlas["cities"].get(primary, {})
        city_name = city.get("name", primary)
        region = city.get("region", "Unknown Region")
        name = prop.get("name", agent_id)

        return f"{name} @ {city_name}, {region}"

    def update_last_seen(self, agent_id: str) -> None:
        """Update last-seen timestamp for an agent (called on heartbeat)."""
        if agent_id in self._properties:
            self._properties[agent_id]["last_seen"] = int(time.time())
            self._save_properties()

    # ── Population Density ──

    def _update_population_stats(self) -> None:
        """Recalculate population density statistics."""
        total_agents = len(self._properties)
        total_cities = len(self._atlas["cities"])

        region_pop: Dict[str, int] = {}
        for city in self._atlas["cities"].values():
            region = city.get("region", "Unknown")
            region_pop[region] = region_pop.get(region, 0) + city.get("population", 0)

        self._atlas["population"] = {
            "total_agents": total_agents,
            "total_cities": total_cities,
            "density": round(total_agents / max(total_cities, 1), 2),
            "by_region": region_pop,
            "updated_at": int(time.time()),
        }

    def population_stats(self) -> Dict[str, Any]:
        """Get current population statistics."""
        self._update_population_stats()
        return dict(self._atlas["population"])

    def density_map(self) -> List[Dict[str, Any]]:
        """Get population density map — cities sorted by density.

        Returns list of {city, region, population, type, density_rank}.
        """
        cities = []
        for domain, city in self._atlas["cities"].items():
            cities.append({
                "domain": domain,
                "city": city.get("name", domain),
                "region": city.get("region", ""),
                "population": city.get("population", 0),
                "type": city.get("type", "outpost"),
            })

        cities.sort(key=lambda c: c["population"], reverse=True)

        for i, c in enumerate(cities):
            c["density_rank"] = i + 1

        return cities

    def hotspots(self, min_population: int = 5) -> List[Dict[str, Any]]:
        """Find population hotspots — cities above a threshold."""
        return [
            c for c in self.density_map()
            if c["population"] >= min_population
        ]

    def rural_properties(self, max_population: int = 3) -> List[Dict[str, Any]]:
        """Find rural/niche areas with low population.

        These are valuable for specialists — less competition, unique positioning.
        """
        return [
            c for c in self.density_map()
            if 0 < c["population"] <= max_population
        ]

    # ── AI-to-AI Calibration Metrics ──

    def calibrate(self, agent_a: str, agent_b: str,
                  trust_mgr: Any = None, accord_mgr: Any = None,
                  interaction_data: Optional[Dict] = None) -> CalibrationResult:
        """Measure calibration between two agents.

        Calibration score components:
        - domain_overlap: How much their capability domains overlap (Jaccard)
        - trust_score: Historical trust from TrustManager
        - response_coherence: Quality metric from interaction data
        - latency_score: Communication latency quality
        - accord_bonus: Bonus if they have an active accord
        """
        scores: Dict[str, float] = {}

        # 1. Domain overlap (Jaccard similarity)
        prop_a = self._properties.get(agent_a, {})
        prop_b = self._properties.get(agent_b, {})
        domains_a = set(prop_a.get("cities", []))
        domains_b = set(prop_b.get("cities", []))

        if domains_a or domains_b:
            intersection = domains_a & domains_b
            union = domains_a | domains_b
            scores["domain_overlap"] = len(intersection) / len(union) if union else 0.0
        else:
            scores["domain_overlap"] = 0.0

        # 2. Trust score
        if trust_mgr:
            try:
                trust_data = trust_mgr.score(agent_b if agent_a else agent_a)
                scores["trust_score"] = min(trust_data.get("score", 0.5), 1.0)
            except Exception:
                scores["trust_score"] = 0.5
        else:
            scores["trust_score"] = 0.5  # Neutral default

        # 3. Response coherence (from interaction data)
        if interaction_data:
            # Coherence based on: response relevance, completion rate, error rate
            relevance = interaction_data.get("relevance", 0.7)
            completion = interaction_data.get("completion_rate", 0.8)
            error_rate = interaction_data.get("error_rate", 0.1)
            scores["response_coherence"] = (relevance * 0.5 + completion * 0.3 + (1.0 - error_rate) * 0.2)
        else:
            scores["response_coherence"] = 0.5

        # 4. Latency score (lower latency = higher score)
        if interaction_data and "latency_ms" in interaction_data:
            latency_ms = interaction_data["latency_ms"]
            # Sigmoid-like: 100ms → 0.95, 1000ms → 0.5, 5000ms → 0.1
            scores["latency_score"] = 1.0 / (1.0 + math.exp((latency_ms - 1000) / 500))
        else:
            scores["latency_score"] = 0.5

        # 5. Accord bonus
        if accord_mgr:
            try:
                accord = accord_mgr.find_accord_with(agent_b)
                scores["accord_bonus"] = 1.0 if accord and accord.get("state") == "active" else 0.0
            except Exception:
                scores["accord_bonus"] = 0.0
        else:
            scores["accord_bonus"] = 0.0

        result = CalibrationResult(agent_a, agent_b, scores)
        self._append_calibration(result.to_dict())
        return result

    def calibration_history(self, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get calibration history for an agent."""
        path = self._calibrations_path()
        if not path.exists():
            return []

        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("agent_a") == agent_id or entry.get("agent_b") == agent_id:
                    entries.append(entry)
            except Exception:
                continue

        return entries[-limit:]

    def best_neighbors(self, agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Find agents with highest calibration scores — the best "neighbors".

        These are the agents this agent works best with.
        """
        history = self.calibration_history(agent_id, limit=500)

        # Aggregate by peer
        peer_scores: Dict[str, List[float]] = {}
        for entry in history:
            peer = entry["agent_b"] if entry["agent_a"] == agent_id else entry["agent_a"]
            peer_scores.setdefault(peer, []).append(entry.get("overall", 0.0))

        # Average scores per peer
        neighbors = []
        for peer, scores_list in peer_scores.items():
            avg = sum(scores_list) / len(scores_list)
            prop = self._properties.get(peer, {})
            neighbors.append({
                "agent_id": peer,
                "name": prop.get("name", peer),
                "calibration": round(avg, 4),
                "interactions": len(scores_list),
                "address": self.agent_address(peer),
            })

        neighbors.sort(key=lambda n: n["calibration"], reverse=True)
        return neighbors[:limit]

    # ── Opportunity Routing ──

    def opportunities_near(self, agent_id: str) -> List[Dict[str, Any]]:
        """Find opportunities near an agent based on their city/region.

        Opportunities = other agents in same cities who could collaborate,
        plus agents in neighboring cities within the same region.
        """
        prop = self._properties.get(agent_id)
        if not prop:
            return []

        my_cities = set(prop.get("cities", []))
        my_regions = set()
        for domain in my_cities:
            city = self._atlas["cities"].get(domain, {})
            my_regions.add(city.get("region", ""))

        opportunities = []
        for other_id, other_prop in self._properties.items():
            if other_id == agent_id:
                continue

            other_cities = set(other_prop.get("cities", []))
            shared_cities = my_cities & other_cities
            other_regions = set()
            for d in other_cities:
                c = self._atlas["cities"].get(d, {})
                other_regions.add(c.get("region", ""))
            shared_regions = my_regions & other_regions

            if shared_cities:
                proximity = "same_city"
            elif shared_regions:
                proximity = "same_region"
            else:
                continue  # Too far — not an opportunity

            opportunities.append({
                "agent_id": other_id,
                "name": other_prop.get("name", other_id),
                "proximity": proximity,
                "shared_cities": list(shared_cities),
                "shared_regions": list(shared_regions),
                "address": self.agent_address(other_id),
            })

        # Same-city opportunities first, then same-region
        opportunities.sort(key=lambda o: (0 if o["proximity"] == "same_city" else 1))
        return opportunities

    # ── Census & Reporting ──

    def census(self) -> Dict[str, Any]:
        """Full census report of the atlas."""
        stats = self.population_stats()
        density = self.density_map()

        metropolises = [c for c in density if c["type"] in ("metropolis", "megalopolis")]
        rural = [c for c in density if c["type"] in ("outpost", "village")]

        return {
            "total_agents": stats.get("total_agents", 0),
            "total_cities": stats.get("total_cities", 0),
            "overall_density": stats.get("density", 0),
            "metropolises": len(metropolises),
            "rural_areas": len(rural),
            "by_region": stats.get("by_region", {}),
            "top_cities": density[:5],
            "quietest_cities": [c for c in reversed(density) if c["population"] > 0][:5],
            "ts": int(time.time()),
        }

    def region_report(self, region: str) -> Dict[str, Any]:
        """Detailed report for a specific region."""
        cities = self.cities_by_region(region)
        total_pop = sum(c.get("population", 0) for c in cities)

        return {
            "region": region,
            "description": REGIONS.get(region, "Unknown region"),
            "cities": len(cities),
            "total_population": total_pop,
            "city_list": [
                {
                    "domain": c.get("domain", ""),
                    "name": c.get("name", ""),
                    "type": c.get("type", "outpost"),
                    "population": c.get("population", 0),
                }
                for c in sorted(cities, key=lambda x: x.get("population", 0), reverse=True)
            ],
        }

    # ── Districts (sub-specializations within a city) ──

    def add_district(self, domain: str, district_name: str,
                     specialty: str = "") -> Dict[str, Any]:
        """Add a district to a city — a sub-specialization.

        e.g., "coding" city might have districts: "python", "rust", "javascript"
        """
        city = self.ensure_city(domain)
        if "districts" not in city:
            city["districts"] = {}

        city["districts"][district_name.lower()] = {
            "name": district_name,
            "specialty": specialty,
            "established_at": int(time.time()),
            "residents": [],
        }

        self._save_atlas()
        return city["districts"][district_name.lower()]

    def join_district(self, agent_id: str, domain: str, district_name: str) -> bool:
        """Join a district within a city."""
        city = self._atlas["cities"].get(domain.lower())
        if not city:
            return False

        district = city.get("districts", {}).get(district_name.lower())
        if not district:
            return False

        if agent_id not in district["residents"]:
            district["residents"].append(agent_id)
            self._save_atlas()

        return True

    # ══════════════════════════════════════════════════════════════════════
    #  PROPERTY VALUATION — "Zillow for AI Agent Addresses"
    # ══════════════════════════════════════════════════════════════════════

    def _valuations_path(self) -> Path:
        return self._dir / VALUATIONS_FILE

    def _market_history_path(self) -> Path:
        return self._dir / MARKET_HISTORY_FILE

    def _append_valuation(self, entry: Dict[str, Any]) -> None:
        path = self._valuations_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def _append_market_history(self, entry: Dict[str, Any]) -> None:
        path = self._market_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    # ── BeaconEstimate (the "Zestimate") ──

    def estimate(self, agent_id: str,
                 trust_mgr: Any = None,
                 accord_mgr: Any = None,
                 heartbeat_mgr: Any = None) -> Dict[str, Any]:
        """Calculate property value estimate for an agent.

        The BeaconEstimate is a composite score (0-1000) based on:
          - Location value:  City population & type (0-200)
          - Scarcity bonus:  Inverse of domain competition (0-150)
          - Network quality: Average calibration with neighbors (0-200)
          - Reputation:      Trust score from interactions (0-200)
          - Uptime:          Heartbeat consistency (0-100)
          - Bonds:           Active accord count (0-150)

        Like Zillow's Zestimate, this is an algorithmic estimate, not gospel.
        """
        prop = self._properties.get(agent_id)
        if not prop:
            return {"error": f"Agent {agent_id} not registered in atlas"}

        now = int(time.time())
        components: Dict[str, float] = {}

        # 1. Location Value (0-200)
        # Based on primary city population and type
        primary = prop.get("primary_city", "")
        city = self._atlas["cities"].get(primary, {})
        population = city.get("population", 0)
        city_type = city.get("type", "outpost")

        type_multipliers = {
            "outpost": 0.2, "village": 0.4, "town": 0.6,
            "city": 0.8, "metropolis": 0.9, "megalopolis": 1.0,
        }
        # Log scale — diminishing returns on huge populations
        pop_score = min(math.log2(max(population, 1) + 1) / 7.0, 1.0)
        type_score = type_multipliers.get(city_type, 0.2)
        components["location"] = round((pop_score * 0.6 + type_score * 0.4) * 200, 1)

        # 2. Scarcity Bonus (0-150)
        # Fewer agents in your domain = higher scarcity value
        # A lone specialist in "vintage" is worth more than agent #50 in "coding"
        total_agents = len(self._properties)
        if total_agents > 0 and population > 0:
            domain_share = population / total_agents
            # Inverse: rare domains score high
            scarcity = max(1.0 - domain_share, 0.0)
            # Bonus for being in a rural area (fewer than 5 agents)
            rural_bonus = 0.3 if population <= 3 else 0.0
            components["scarcity"] = round(min((scarcity + rural_bonus), 1.0) * 150, 1)
        else:
            components["scarcity"] = 75.0  # Neutral when no data

        # 3. Network Quality (0-200)
        # Average calibration score with neighbors
        cal_history = self.calibration_history(agent_id, limit=100)
        if cal_history:
            avg_cal = sum(e.get("overall", 0) for e in cal_history) / len(cal_history)
            unique_peers = len(set(
                e["agent_b"] if e["agent_a"] == agent_id else e["agent_a"]
                for e in cal_history
            ))
            # More calibrated peers = more valuable network
            peer_breadth = min(unique_peers / 10.0, 1.0)
            components["network"] = round((avg_cal * 0.7 + peer_breadth * 0.3) * 200, 1)
        else:
            components["network"] = 0.0

        # 4. Reputation (0-200)
        if trust_mgr:
            try:
                trust_data = trust_mgr.score(agent_id)
                score = min(trust_data.get("score", 0.5), 1.0)
                total_interactions = trust_data.get("total", 0)
                # More interactions = more reliable score
                confidence = min(total_interactions / 20.0, 1.0)
                components["reputation"] = round(score * confidence * 200, 1)
            except Exception:
                components["reputation"] = 100.0
        else:
            components["reputation"] = 100.0  # Neutral

        # 5. Uptime (0-100)
        if heartbeat_mgr:
            try:
                own = heartbeat_mgr.own_status()
                beat_count = own.get("beat_count", 0)
                # More beats = more reliable
                uptime_score = min(beat_count / 100.0, 1.0)
                components["uptime"] = round(uptime_score * 100, 1)
            except Exception:
                components["uptime"] = 0.0
        else:
            components["uptime"] = 0.0

        # 6. Bonds (0-150)
        if accord_mgr:
            try:
                accords = accord_mgr.active_accords()
                accord_count = len(accords) if isinstance(accords, list) else 0
                # Each accord is valuable — diminishing returns
                bond_score = min(math.log2(accord_count + 1) / 3.0, 1.0)
                components["bonds"] = round(bond_score * 150, 1)
            except Exception:
                components["bonds"] = 0.0
        else:
            components["bonds"] = 0.0

        # Total BeaconEstimate (0-1000)
        total = sum(components.values())
        total = round(min(total, 1000.0), 1)

        # Grade: S/A/B/C/D/F
        if total >= 800:
            grade = "S"
        elif total >= 650:
            grade = "A"
        elif total >= 500:
            grade = "B"
        elif total >= 350:
            grade = "C"
        elif total >= 200:
            grade = "D"
        else:
            grade = "F"

        estimate_record = {
            "agent_id": agent_id,
            "address": self.agent_address(agent_id),
            "estimate": total,
            "grade": grade,
            "components": components,
            "max_possible": 1000,
            "ts": now,
        }

        self._append_valuation(estimate_record)
        return estimate_record

    # ── Comparable Agents ("Comps") ──

    def comps(self, agent_id: str, limit: int = 5,
              trust_mgr: Any = None, accord_mgr: Any = None,
              heartbeat_mgr: Any = None) -> List[Dict[str, Any]]:
        """Find comparable agents — similar domain profile, same city/region.

        Like real estate comps: "Here are 5 similar properties near you."
        Returns agents sorted by similarity to the target.
        """
        prop = self._properties.get(agent_id)
        if not prop:
            return []

        my_domains = set(prop.get("cities", []))
        my_primary = prop.get("primary_city", "")
        my_city = self._atlas["cities"].get(my_primary, {})
        my_region = my_city.get("region", "")

        candidates = []
        for other_id, other_prop in self._properties.items():
            if other_id == agent_id:
                continue

            other_domains = set(other_prop.get("cities", []))
            other_primary = other_prop.get("primary_city", "")
            other_city = self._atlas["cities"].get(other_primary, {})
            other_region = other_city.get("region", "")

            # Similarity: domain Jaccard + location bonus
            union = my_domains | other_domains
            intersection = my_domains & other_domains
            domain_sim = len(intersection) / len(union) if union else 0.0

            location_bonus = 0.0
            if my_primary == other_primary:
                location_bonus = 0.3  # Same city
            elif my_region == other_region:
                location_bonus = 0.15  # Same region

            similarity = domain_sim * 0.7 + location_bonus

            candidates.append({
                "agent_id": other_id,
                "name": other_prop.get("name", other_id),
                "address": self.agent_address(other_id),
                "similarity": round(similarity, 4),
                "shared_domains": list(intersection),
                "primary_city": other_primary,
            })

        # Sort by similarity descending
        candidates.sort(key=lambda c: c["similarity"], reverse=True)
        top = candidates[:limit]

        # Optionally estimate their values too
        for comp in top:
            est = self.estimate(comp["agent_id"],
                                trust_mgr=trust_mgr,
                                accord_mgr=accord_mgr,
                                heartbeat_mgr=heartbeat_mgr)
            comp["estimate"] = est.get("estimate", 0)
            comp["grade"] = est.get("grade", "?")

        return top

    # ── Property Listing ──

    def listing(self, agent_id: str,
                trust_mgr: Any = None, accord_mgr: Any = None,
                heartbeat_mgr: Any = None) -> Dict[str, Any]:
        """Generate a full property listing for an agent.

        Like a Zillow listing page: address, estimate, photos (stats),
        neighborhood info, comparable properties.
        """
        prop = self._properties.get(agent_id)
        if not prop:
            return {"error": f"Agent {agent_id} not registered"}

        est = self.estimate(agent_id, trust_mgr=trust_mgr,
                            accord_mgr=accord_mgr,
                            heartbeat_mgr=heartbeat_mgr)

        primary = prop.get("primary_city", "")
        city = self._atlas["cities"].get(primary, {})

        # Neighborhood info
        neighbors_list = self.best_neighbors(agent_id, limit=5)
        nearby_opps = self.opportunities_near(agent_id)

        comparable = self.comps(agent_id, limit=3,
                                trust_mgr=trust_mgr,
                                accord_mgr=accord_mgr,
                                heartbeat_mgr=heartbeat_mgr)

        return {
            "listing": {
                "agent_id": agent_id,
                "name": prop.get("name", agent_id),
                "address": self.agent_address(agent_id),
                "registered_since": prop.get("registered_at", 0),
                "last_active": prop.get("last_seen", 0),
                "domains": prop.get("cities", []),
            },
            "valuation": {
                "beacon_estimate": est.get("estimate", 0),
                "grade": est.get("grade", "?"),
                "components": est.get("components", {}),
            },
            "neighborhood": {
                "city": city.get("name", primary),
                "region": city.get("region", ""),
                "city_type": city.get("type", "outpost"),
                "city_population": city.get("population", 0),
                "districts": list(city.get("districts", {}).keys()),
            },
            "social": {
                "top_neighbors": neighbors_list[:3],
                "opportunities_nearby": len(nearby_opps),
                "calibrated_peers": len(self.calibration_history(agent_id, limit=100)),
            },
            "comparables": comparable,
            "ts": int(time.time()),
        }

    # ── Market Trends ──

    def snapshot_market(self) -> Dict[str, Any]:
        """Take a snapshot of the current market — call periodically.

        Saves to market_history.jsonl for trend analysis.
        """
        now = int(time.time())
        snapshot = {
            "ts": now,
            "total_agents": len(self._properties),
            "total_cities": len(self._atlas["cities"]),
            "cities": {},
        }

        for domain, city in self._atlas["cities"].items():
            snapshot["cities"][domain] = {
                "population": city.get("population", 0),
                "type": city.get("type", "outpost"),
                "region": city.get("region", ""),
            }

        self._append_market_history(snapshot)
        return snapshot

    def market_trends(self, limit: int = 30) -> Dict[str, Any]:
        """Analyze market trends from historical snapshots.

        Returns per-city growth rates, hottest/coldest markets,
        and overall network growth.
        """
        path = self._market_history_path()
        if not path.exists():
            return {"message": "No market history yet. Run snapshot_market() first."}

        snapshots = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                snapshots.append(json.loads(line))
            except Exception:
                continue

        snapshots = snapshots[-limit:]
        if len(snapshots) < 2:
            return {"message": "Need at least 2 snapshots for trend analysis.",
                    "snapshots": len(snapshots)}

        first = snapshots[0]
        latest = snapshots[-1]
        time_span_s = latest["ts"] - first["ts"]
        time_span_days = max(time_span_s / 86400, 0.01)

        # Overall growth
        agent_growth = latest["total_agents"] - first["total_agents"]
        city_growth = latest["total_cities"] - first["total_cities"]

        # Per-city trends
        city_trends: Dict[str, Dict[str, Any]] = {}
        latest_cities = latest.get("cities", {})
        first_cities = first.get("cities", {})

        for domain in set(list(latest_cities.keys()) + list(first_cities.keys())):
            old_pop = first_cities.get(domain, {}).get("population", 0)
            new_pop = latest_cities.get(domain, {}).get("population", 0)
            delta = new_pop - old_pop

            city_info = latest_cities.get(domain, first_cities.get(domain, {}))
            city_trends[domain] = {
                "name": self._atlas["cities"].get(domain, {}).get("name", domain),
                "region": city_info.get("region", ""),
                "current_population": new_pop,
                "change": delta,
                "growth_rate": round(delta / max(old_pop, 1) * 100, 1),
                "trend": "growing" if delta > 0 else ("declining" if delta < 0 else "stable"),
            }

        # Sort by growth
        hottest = sorted(city_trends.values(), key=lambda c: c["change"], reverse=True)
        coldest = sorted(city_trends.values(), key=lambda c: c["change"])

        return {
            "period": {
                "from": first["ts"],
                "to": latest["ts"],
                "days": round(time_span_days, 1),
                "snapshots": len(snapshots),
            },
            "overall": {
                "agent_growth": agent_growth,
                "agent_growth_rate": round(agent_growth / max(first["total_agents"], 1) * 100, 1),
                "city_growth": city_growth,
                "current_agents": latest["total_agents"],
                "current_cities": latest["total_cities"],
            },
            "hottest_markets": [c for c in hottest if c["change"] > 0][:5],
            "coldest_markets": [c for c in coldest if c["change"] < 0][:5],
            "stable_markets": [c for c in city_trends.values() if c["change"] == 0],
            "all_cities": city_trends,
        }

    # ── Valuation History ──

    def valuation_history(self, agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get historical valuations for an agent — track appreciation."""
        path = self._valuations_path()
        if not path.exists():
            return []

        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("agent_id") == agent_id:
                    entries.append(entry)
            except Exception:
                continue

        return entries[-limit:]

    def appreciation(self, agent_id: str) -> Dict[str, Any]:
        """Calculate property value appreciation over time."""
        history = self.valuation_history(agent_id)
        if len(history) < 2:
            return {
                "agent_id": agent_id,
                "message": "Need at least 2 valuations to calculate appreciation.",
                "valuations": len(history),
            }

        first = history[0]
        latest = history[-1]
        time_span_s = latest["ts"] - first["ts"]
        time_span_days = max(time_span_s / 86400, 0.01)

        value_change = latest["estimate"] - first["estimate"]
        pct_change = round(value_change / max(first["estimate"], 1) * 100, 1)
        daily_rate = round(value_change / time_span_days, 2)

        # Grade trajectory
        grades = [h.get("grade", "?") for h in history]
        grade_order = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1, "F": 0, "?": -1}
        grade_values = [grade_order.get(g, -1) for g in grades]
        grade_trend = "improving" if grade_values[-1] > grade_values[0] else (
            "declining" if grade_values[-1] < grade_values[0] else "stable"
        )

        return {
            "agent_id": agent_id,
            "address": self.agent_address(agent_id),
            "first_estimate": first["estimate"],
            "current_estimate": latest["estimate"],
            "change": round(value_change, 1),
            "change_pct": pct_change,
            "daily_rate": daily_rate,
            "period_days": round(time_span_days, 1),
            "grade_history": grades,
            "grade_trend": grade_trend,
            "valuations_count": len(history),
        }

    # ── Leaderboard ──

    def leaderboard(self, limit: int = 10,
                    trust_mgr: Any = None, accord_mgr: Any = None,
                    heartbeat_mgr: Any = None) -> List[Dict[str, Any]]:
        """Top agents by property value — the "most valuable addresses."

        Runs estimate() on all registered agents and ranks them.
        """
        board = []
        for agent_id in list(self._properties.keys()):
            est = self.estimate(agent_id, trust_mgr=trust_mgr,
                                accord_mgr=accord_mgr,
                                heartbeat_mgr=heartbeat_mgr)
            if "error" not in est:
                board.append({
                    "rank": 0,
                    "agent_id": agent_id,
                    "name": self._properties[agent_id].get("name", agent_id),
                    "address": est.get("address", ""),
                    "estimate": est.get("estimate", 0),
                    "grade": est.get("grade", "?"),
                })

        board.sort(key=lambda b: b["estimate"], reverse=True)
        for i, entry in enumerate(board):
            entry["rank"] = i + 1

        return board[:limit]
