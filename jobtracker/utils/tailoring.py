# utils/tailoring.py

import re
from textwrap import dedent

TECH_KEYWORDS = [
    # CI/CD
    "ci/cd",
    "continuous integration",
    "continuous delivery",
    "continuous deployment",
    "jenkins",
    "github actions",
    "gitlab ci",
    "argo cd",
    "argo workflows",
    "azure devops",

    # Containers / K8s
    "kubernetes",
    "eks",
    "gke",
    "aks",
    "docker",
    "helm",
    "istio",
    "service mesh",

    # IaC
    "terraform",
    "pulumi",
    "infrastructure as code",
    "iac",
    "ansible",
    "chef",
    "puppet",

    # Cloud
    "aws",
    "amazon web services",
    "gcp",
    "google cloud",
    "azure",

    # Observability
    "observability",
    "monitoring",
    "alerting",
    "prometheus",
    "grafana",
    "loki",
    "tempo",
    "mimir",
    "opentelemetry",
    "otel",
    "datadog",
    "new relic",
    "splunk",
    "elk",
    "elasticsearch",
    "kibana",
    "logstash",

    # Messaging / data
    "kafka",
    "rabbitmq",
    "sqs",
    "sns",

    # Languages / scripting
    "python",
    "golang",
    "go",
    "bash",
    "shell scripting",

    # SRE / reliability
    "sre",
    "site reliability",
    "incident response",
    "on-call",
    "on call",
    "slo",
    "slos",
    "error budget",
    "error budgets",
]

ROLE_KEYWORDS = [
    "site reliability",
    "sre",
    "devops",
    "platform engineer",
    "infrastructure engineer",
    "cloud engineer",
    "systems engineer",
    "production engineer",
]


def _extract_keywords(jd_text: str) -> list[str]:
    text = jd_text.lower()
    found = []
    for kw in TECH_KEYWORDS:
        if kw in text and kw not in found:
            found.append(kw)
    return found


def _normalize_title(job_title: str) -> str:
    if not job_title:
        return "Senior Site Reliability Engineer"
    return job_title.strip()


def generate_tailored_sections(job_title: str, company: str, jd_text: str) -> dict:
    """
    Given job title, company, and JD text, generate:
      - headline
      - summary
      - skills_block
      - bullets (list of strings)
      - why_fit
      - keywords_block
    """
    title = _normalize_title(job_title)
    company = (company or "").strip() or "the company"
    jd_text = jd_text or ""
    lower_jd = jd_text.lower()

    keywords = _extract_keywords(jd_text)
    top_keywords = keywords[:6]

    # Headline
    if top_keywords:
        headline = f"{title} | " + " • ".join([kw.title() for kw in top_keywords[:4]])
    else:
        headline = f"{title} | Kubernetes • Terraform • Python • Observability"

    # Summary
    tools_snippet = (
        ", ".join(kw.title() for kw in top_keywords[:4])
        if top_keywords
        else "Kubernetes, Terraform, Python, Observability"
    )
    summary = dedent(
        f"""
        Senior Cloud / Site Reliability Engineer with 8+ years of experience building and operating large-scale, cloud-native systems.
        Strong background in SRE practices, automation, and internal tooling, with hands-on work in {tools_snippet}.
        Well-aligned with {company}'s focus on reliability, observability, and improving engineering productivity for microservice-based platforms.
        """
    ).strip()

    # Skills block
    skills_line = (
        ", ".join(kw.title() for kw in top_keywords) if top_keywords else tools_snippet
    )
    skills_block = f"Relevant Skills for this Role: {skills_line}"

    # Bullets for Viant-type role
    bullets: list[str] = []

    if any(k in lower_jd for k in ["kubernetes", "eks", "gke", "aks", "container"]):
        bullets.append(
            "Designed and operated Kubernetes-based platforms (EKS/GKE) for high-throughput services using Helm, GitOps, and safe deployment strategies."
        )

    if any(k in lower_jd for k in ["terraform", "infrastructure as code", "iac"]):
        bullets.append(
            "Built and maintained Terraform-based Infrastructure-as-Code modules for multi-environment, multi-region workloads, improving consistency and reducing provisioning time."
        )

    if any(k in lower_jd for k in ["observability", "prometheus", "datadog", "grafana", "loki", "otel", "opentelemetry"]):
        bullets.append(
            "Implemented observability standards using metrics, logs, and traces (Prometheus, Grafana, Loki, Datadog, OpenTelemetry), significantly improving visibility and MTTR."
        )

    if any(k in lower_jd for k in ["ci/cd", "pipeline", "github actions", "jenkins", "gitlab ci"]):
        bullets.append(
            "Modernized CI/CD pipelines (GitHub Actions / Jenkins) with automated testing, validation, and safe rollout/rollback workflows, reducing deployment-related incidents."
        )

    if any(k in lower_jd for k in ["incident", "on-call", "on call", "slo", "error budget"]):
        bullets.append(
            "Led SRE incident response and on-call rotations, driving root cause analysis and permanent fixes aligned with SLOs and error budgets."
        )

    if not bullets:
        bullets.extend(
            [
                "Built internal SRE tooling in Python/Go to reduce operational toil and automate common reliability workflows.",
                "Drove improvements in monitoring, alerting, and production readiness across multiple services and teams.",
            ]
        )

    why_fit = dedent(
        f"""
        I’m a strong fit for the {title} role at {company} because my background closely matches your focus on reliability engineering, automation, and observability.
        I have hands-on experience building internal tooling, standardizing Kubernetes/Terraform-based infrastructure, and improving CI/CD and incident response processes.
        I enjoy partnering with product and engineering teams to raise operational maturity, reduce toil, and create reliable, data-driven systems that directly improve customer experience.
        """
    ).strip()

    keywords_block = ", ".join(keywords) if keywords else ""

    return {
        "headline": headline,
        "summary": summary,
        "skills_block": skills_block,
        "bullets": bullets,
        "why_fit": why_fit,
        "keywords_block": keywords_block,
    }

