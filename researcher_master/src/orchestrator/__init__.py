from .orchestrator import Orchestrator, discovery_agent, ingest_agent, verifier_agent

# Single global orchestrator instance for the app
orchestrator = Orchestrator()

# Register default stub agents
orchestrator.register_agent("discovery", discovery_agent)
orchestrator.register_agent("ingest", ingest_agent)
orchestrator.register_agent("verifier", verifier_agent)

__all__ = ["Orchestrator", "orchestrator", "discovery_agent", "ingest_agent", "verifier_agent"]
