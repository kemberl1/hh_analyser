"""Rule-based skill matching — Phase 7.

Extracts skills from sanitised resume text and matches them against
market-demanded skills from the aggregation layer.

Uses a canonical skill dictionary (same as normalizer's skill_aliases)
to find both exact and fuzzy matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Canonical Frontend skill dictionary
# Maps lowercase aliases → canonical name
# Based on common frontend vacancy skills from hh.ru
# ---------------------------------------------------------------------------

SKILL_ALIASES: dict[str, str] = {
    # Core web
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "scss": "CSS",
    "sass": "CSS",
    "less": "CSS",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "tailwind css": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    # JavaScript
    "javascript": "JavaScript",
    "js": "JavaScript",
    "es6": "JavaScript",
    "es2015": "JavaScript",
    "ecmascript": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    # React ecosystem
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "react js": "React",
    "redux": "Redux",
    "redux toolkit": "Redux",
    "mobx": "MobX",
    "zustand": "Zustand",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "next js": "Next.js",
    "next": "Next.js",
    "gatsby": "Gatsby",
    "react native": "React Native",
    "react-native": "React Native",
    # Vue ecosystem
    "vue": "Vue.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "vue js": "Vue.js",
    "vue3": "Vue.js",
    "vue 3": "Vue.js",
    "vuex": "Vuex",
    "pinia": "Pinia",
    "nuxt": "Nuxt.js",
    "nuxt.js": "Nuxt.js",
    "nuxtjs": "Nuxt.js",
    # Angular
    "angular": "Angular",
    "angularjs": "Angular",
    "angular.js": "Angular",
    "rxjs": "RxJS",
    "ngrx": "NgRx",
    # Build tools
    "webpack": "Webpack",
    "vite": "Vite",
    "rollup": "Rollup",
    "parcel": "Parcel",
    "esbuild": "esbuild",
    "babel": "Babel",
    "swc": "SWC",
    # Testing
    "jest": "Jest",
    "vitest": "Vitest",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "testing library": "Testing Library",
    "react testing library": "Testing Library",
    "rtl": "Testing Library",
    "storybook": "Storybook",
    "selenium": "Selenium",
    "puppeteer": "Puppeteer",
    # State / data
    "graphql": "GraphQL",
    "apollo": "Apollo",
    "rest api": "REST API",
    "rest": "REST API",
    "axios": "Axios",
    "fetch api": "Fetch API",
    "tanstack query": "TanStack Query",
    "react query": "TanStack Query",
    "swr": "SWR",
    # CSS frameworks / UI
    "material ui": "Material UI",
    "mui": "Material UI",
    "ant design": "Ant Design",
    "antd": "Ant Design",
    "chakra ui": "Chakra UI",
    "styled-components": "Styled Components",
    "styled components": "Styled Components",
    "css modules": "CSS Modules",
    "css-in-js": "CSS-in-JS",
    "emotion": "Emotion",
    "shadcn": "shadcn/ui",
    # Version control & CI
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "ci/cd": "CI/CD",
    "ci cd": "CI/CD",
    "docker": "Docker",
    # Other
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "node": "Node.js",
    "npm": "npm",
    "yarn": "Yarn",
    "pnpm": "pnpm",
    "figma": "Figma",
    "responsive": "Responsive Design",
    "responsive design": "Responsive Design",
    "адаптивная вёрстка": "Responsive Design",
    "адаптивная верстка": "Responsive Design",
    "кроссбраузерность": "Cross-browser",
    "cross-browser": "Cross-browser",
    "accessibility": "Accessibility",
    "a11y": "Accessibility",
    "seo": "SEO",
    "ssr": "SSR",
    "pwa": "PWA",
    "web components": "Web Components",
    "webgl": "WebGL",
    "three.js": "Three.js",
    "d3": "D3.js",
    "d3.js": "D3.js",
    "recharts": "Recharts",
    "echarts": "ECharts",
    "chart.js": "Chart.js",
    "websocket": "WebSocket",
    "websockets": "WebSocket",
    "socket.io": "Socket.IO",
    "agile": "Agile",
    "scrum": "Scrum",
    "kanban": "Kanban",
    "jira": "Jira",
    "верстка": "HTML/CSS вёрстка",
    "вёрстка": "HTML/CSS вёрстка",
    "pixel perfect": "Pixel Perfect",
    "бэм": "BEM",
    "bem": "BEM",
    "svelte": "Svelte",
    "solid": "SolidJS",
    "solidjs": "SolidJS",
    "astro": "Astro",
    "remix": "Remix",
    "microfrontend": "Micro Frontends",
    "micro frontend": "Micro Frontends",
    "микрофронтенд": "Micro Frontends",
    "monorepo": "Monorepo",
    "turborepo": "Turborepo",
    "nx": "Nx",
    "lerna": "Lerna",
    "redux-saga": "Redux Saga",
    "redux saga": "Redux Saga",
    "effector": "Effector",
    "recoil": "Recoil",
    "formik": "Formik",
    "react hook form": "React Hook Form",
    "zod": "Zod",
    "yup": "Yup",
    "i18n": "i18n",
    "интернационализация": "i18n",
    "eslint": "ESLint",
    "prettier": "Prettier",
    "lint": "Linting",
    "husky": "Husky",
}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class SkillMatchResult:
    """Result of skill extraction and market matching."""
    resume_skills: list[str]  # canonical skills found in resume
    matched_skills: list[str]  # skills that are also in market top
    missing_skills: list[str]  # market top skills NOT in resume
    match_ratio: float  # matched / total market top skills
    extra_skills: list[str]  # resume skills not in market top (bonus)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_skills_from_text(text: str) -> list[str]:
    """Extract canonical skill names from resume text using dictionary matching.

    Searches for known skill aliases in the text (case-insensitive, word-boundary).
    Returns deduplicated list of canonical skill names.
    """
    text_lower = text.lower()
    found: dict[str, bool] = {}  # canonical → True (preserves insertion order)

    # Sort aliases by length descending to match longer phrases first
    sorted_aliases = sorted(SKILL_ALIASES.keys(), key=len, reverse=True)

    for alias in sorted_aliases:
        canonical = SKILL_ALIASES[alias]
        if canonical in found:
            continue
        # Word boundary search
        pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        if pattern.search(text_lower):
            found[canonical] = True

    return list(found.keys())


# ---------------------------------------------------------------------------
# Matching against market data
# ---------------------------------------------------------------------------

def match_skills_with_market(
    resume_skills: list[str],
    market_skills: list[dict],
    top_n: int = 20,
) -> SkillMatchResult:
    """Match extracted resume skills against market top skills.

    Parameters
    ----------
    resume_skills : canonical skill names from resume.
    market_skills : list of dicts with 'skill'/'name' and 'share' from aggregation.
    top_n : how many top market skills to consider.

    Returns
    -------
    SkillMatchResult with matched/missing/extra skills and match ratio.
    """
    # Normalise market skill names for comparison
    market_top: list[str] = []
    market_names_lower: dict[str, str] = {}  # lower → original
    for s in market_skills[:top_n]:
        name = s.get("skill") or s.get("name") or ""
        if name:
            market_top.append(name)
            market_names_lower[name.lower()] = name

    resume_lower = {s.lower(): s for s in resume_skills}

    matched = []
    for market_name in market_top:
        ml = market_name.lower()
        # Direct match
        if ml in resume_lower:
            matched.append(market_name)
            continue
        # Check if resume has a canonical equivalent
        for rl, rcanonical in resume_lower.items():
            if rcanonical.lower() == ml:
                matched.append(market_name)
                break

    matched_set = {m.lower() for m in matched}
    missing = [m for m in market_top if m.lower() not in matched_set]

    market_top_lower = {m.lower() for m in market_top}
    extra = [s for s in resume_skills if s.lower() not in market_top_lower]

    match_ratio = len(matched) / len(market_top) if market_top else 0.0

    return SkillMatchResult(
        resume_skills=resume_skills,
        matched_skills=matched,
        missing_skills=missing,
        match_ratio=round(match_ratio, 2),
        extra_skills=extra,
    )
