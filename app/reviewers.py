"""Versioned, reproducible panel sampling; these are fictional perspectives."""
import hashlib
import json
import re
import random

VERSION = 1
ARCHETYPES = [
    ('mechanisms', '机制与理论研究者', 'Formal reasoning, algorithms and mechanism design',
     'Trace the central claim through assumptions, invariants and boundary cases. Distinguish an invalid claim from an unstated applicability condition.',
     'A narrow but sound result can be valuable; do not demand scale experiments for a purely theoretical claim.'),
    ('measurement', '实证与测量研究者', 'Experimental methodology, measurement and statistical inference',
     'Audit whether measurements identify the claimed cause; inspect baseline comparability, variability, workload selection and alternative explanations.',
     'Value robust evidence even for incremental contributions. Ask for additional experiments only when they could change the central conclusion.'),
    ('deployment', '部署与工程实践者', 'Production engineering, reliability and real-world deployment',
     'Examine operational assumptions, integration costs, failure modes and whether the claimed benefit survives realistic constraints.',
     'Credit practical simplification and demonstrated utility; do not require production deployment when the paper only claims a prototype result.'),
    ('cross_field', '跨领域方法研究者', 'Transfer of methods across neighboring research areas',
     'Look for conceptual connections and reusable ideas. Evaluate whether the contribution goes beyond relabeling a known mechanism using only supplied evidence.',
     'Give promising ideas credit within the actual venue rubric, while separating potential from demonstrated results. Do not invent prior work.'),
    ('reproduction', '复现与工具研究者', 'Reproducible research, implementation and scientific tooling',
     'Trace what an independent researcher could reconstruct from the stated protocol, implementation details and artifacts described in the paper.',
     'Distinguish reporting gaps from invalid results. Missing code alone is not a rejection reason unless the venue explicitly requires it.'),
    ('adversarial', '稳健性与安全研究者', 'Robustness, security and adversarial reasoning',
     'Stress-test the stated threat model, assumptions and exceptional inputs with concrete thought experiments grounded in the paper.',
     'Only treat a failure case as decisive if it falls inside the claimed scope. Do not impose a security claim on an unrelated paper.'),
    ('synthesis', '领域综合评价者', 'Broad program-committee evaluation and research communication',
     'Identify the main scientific takeaway, audience and contribution relative to the paper’s own related-work evidence; check whether claims match demonstrated scope.',
     'Value a clear, useful research contribution over checklist completeness. Poor exposition lowers confidence only where it obstructs verification.'),
]
CALIBRATIONS = [
    'Evidence-first: unresolved uncertainty in the central claim weighs heavily; peripheral omissions need not block acceptance.',
    'Contribution-first: tolerate explicitly bounded limitations when the central contribution is compelling and supported.',
    'Scope-first: judge success against the stated claim and venue, rewarding honest boundaries rather than breadth alone.',
]


def sample_persona(run, reviewer, conference):
    seed = hashlib.sha256(('reviewer-v1:' + run['id']).encode()).digest()
    rng = random.Random(seed)
    panel = rng.sample(ARCHETYPES, len(ARCHETYPES))
    calibrations = CALIBRATIONS.copy()
    rng.shuffle(calibrations)
    key, name, background, lens, tradeoff = panel[reviewer]
    topics = conference.get('topics', [])
    metadata = json.loads(run.get('snapshot', '{}'))
    # Match only paper content; author identities must not influence reviewer selection.
    paper_text = ' '.join(str(metadata.get(k, '')) for k in ('title','abstract','keywords','topics')).lower()
    candidates = conference.get('public_pc', [])
    ranked = list(candidates)
    rng.shuffle(ranked)
    def match(member):
        terms = set(re.findall(r'[a-z][a-z0-9-]{2,}', ' '.join(member['research_areas']).lower()))
        return sum(bool(re.search(r'\b' + re.escape(t) + r'\b', paper_text)) for t in terms)
    ranked.sort(key=match, reverse=True)
    # Mix close matches with adjacent backgrounds instead of choosing only the top matches.
    order = list(dict.fromkeys(i for i in [0, len(ranked)//2, 1, len(ranked)-1, 2, *range(len(ranked))] if 0 <= i < len(ranked)))
    member = ranked[order[reviewer]] if reviewer < len(order) else None
    return dict(version=VERSION, public_background=member,
                background_use='Public research areas only; fictional reviewer, not the named person or their opinions.',
                matching='Metadata keyword overlap (heuristic); verify relevance from full paper' if member else 'Generic perspective; no verified public PC background available for this slot', archetype=key, name=name, background=background,
                lens=lens, tradeoff=tradeoff, calibration=calibrations[reviewer % len(calibrations)],
                venue_topics=topics,
                expertise_instruction='Identify the paper-specific subfield closest to this background after reading the full paper. State your actual evidence limits; this fictional background is not proof of expertise. Evaluate unfamiliar areas cautiously and calibrate confidence accordingly.')


def paper_focus(run, persona):
    metadata = json.loads(run['snapshot'])
    return {
        'title': metadata.get('title', ''),
        'abstract': metadata.get('abstract', ''),
        'keywords': metadata.get('keywords', []),
        'topics': metadata.get('topics', []),
        'research_background': (persona.get('public_background') or {}).get('research_areas', [persona['background']]),
        'inspection_lens': persona['lens'],
        'decision_tradeoff': persona['tradeoff'],
        'instructions': 'Identify the precise contribution and claimed scope from this metadata, then verify them against the full paper. Connect your research background to specific mechanisms, experiments or arguments. Focus on relevant intersections; do not impose unrelated field conventions. Distinguish a specialist concern from a venue-wide requirement.',
    }
