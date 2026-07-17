from prometheus_client import Counter, Histogram, Summary
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from loguru import logger

# Initialize Prometheus Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total count of HTTP requests",
    ["method", "handler", "status"]
)

AIFLOW_AGENT_LATENCY = Summary(
    "aiflow_agent_latency_seconds",
    "Latency of individual agent nodes in seconds",
    ["agent_name"]
)

AIFLOW_WORKFLOW_EXECUTION = Counter(
    "aiflow_workflow_execution_total",
    "Total count of multi-agent workflows executed",
    ["status"]
)

AIFLOW_AGENT_FAILURES = Counter(
    "aiflow_agent_failures_total",
    "Total count of agent node errors or validation failures"
)

AIFLOW_REDIS_CACHE_HITS = Counter(
    "aiflow_redis_cache_hits_total",
    "Total count of successful Redis cache reads"
)

# OpenTelemetry configuration
def setup_telemetry(app_name: str = "AIFlow-Orchestrator"):
    try:
        provider = TracerProvider(
            resource=Resource.create({"service.name": app_name})
        )
        
        # We output tracing logs to console for visibility, or export to collector if needed.
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry tracing provider successfully initialized.")
    except Exception as e:
        logger.error(f"OpenTelemetry initialization failed: {e}")

tracer = trace.get_tracer("aiflow-orchestrator-tracer")
