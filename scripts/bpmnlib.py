"""Shared BPMN 2.0.2 helpers: namespaces, element taxonomy, model indexing, event
classification and the conformance sub-class tables (OMG formal/2013-12-09, clause 2.2.2).

Pure lxml; no other dependencies.
"""
from __future__ import annotations

import re
from lxml import etree

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
NSMAP_OUT = {None: BPMN_NS, "bpmndi": BPMNDI_NS, "dc": DC_NS, "di": DI_NS, "xsi": XSI_NS}

SKILL_VERSION = "1.0"


def q(local: str, ns: str = BPMN_NS) -> str:
    return "{%s}%s" % (ns, local)


def ln(el) -> str | None:
    """Local name of an element ('' for comments / processing instructions)."""
    if el is None or not isinstance(el.tag, str):
        return ""
    return etree.QName(el.tag).localname


def ns_of(el) -> str | None:
    if el is None or not isinstance(el.tag, str):
        return None
    return etree.QName(el.tag).namespace


def kids(el, *names):
    """Child elements (BPMN namespace) optionally filtered by local name."""
    for c in el.iterchildren("*"):
        if ns_of(c) != BPMN_NS:
            continue
        if not names or ln(c) in names:
            yield c


def text_of(el) -> str:
    return (el.text or "").strip() if el is not None else ""


# ----------------------------------------------------------------------------------------------
# Taxonomy
# ----------------------------------------------------------------------------------------------
TASKS = {"task", "userTask", "serviceTask", "sendTask", "receiveTask", "manualTask",
         "businessRuleTask", "scriptTask"}
SUBPROCS = {"subProcess", "adHocSubProcess", "transaction"}
ACTIVITIES = TASKS | SUBPROCS | {"callActivity"}
EVENTS = {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
          "boundaryEvent", "implicitThrowEvent"}
GATEWAYS = {"exclusiveGateway", "inclusiveGateway", "parallelGateway", "complexGateway",
            "eventBasedGateway"}
CHOREO_ACTS = {"choreographyTask", "subChoreography", "callChoreography"}
FLOW_NODES = ACTIVITIES | EVENTS | GATEWAYS | CHOREO_ACTS
PROCESS_CONTAINERS = {"process", "subProcess", "adHocSubProcess", "transaction"}
CONTAINERS = PROCESS_CONTAINERS | {"choreography", "subChoreography", "globalChoreographyTask"}
DATA_REFS = {"dataObjectReference", "dataStoreReference", "dataInput", "dataOutput", "dataObject",
             "dataStore"}
DATA_VISUAL = {"dataObjectReference", "dataStoreReference", "dataInput", "dataOutput"}
ARTIFACTS = {"textAnnotation", "group"}
CONV_NODES = {"conversation", "subConversation", "callConversation"}
FLOW_ELEMENTS_ALL = FLOW_NODES | DATA_REFS | ARTIFACTS | {"sequenceFlow", "association", "laneSet"}

EVENT_DEF_TAGS = {
    "messageEventDefinition": "message", "timerEventDefinition": "timer",
    "conditionalEventDefinition": "conditional", "linkEventDefinition": "link",
    "signalEventDefinition": "signal", "escalationEventDefinition": "escalation",
    "errorEventDefinition": "error", "cancelEventDefinition": "cancel",
    "compensateEventDefinition": "compensation", "terminateEventDefinition": "terminate",
}

THROW_EVENTS = {"endEvent", "intermediateThrowEvent", "implicitThrowEvent"}


def is_true(v, default=False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() == "true"


def local_id(ref: str | None) -> str | None:
    """Strip a namespace prefix from a QName-style reference ('tns:Process_1' -> 'Process_1')."""
    if ref is None:
        return None
    ref = ref.strip()
    return ref.split(":", 1)[1] if ":" in ref else ref


class Model:
    """A parsed BPMN file with an id index and convenience accessors."""

    def __init__(self, root, path: str | None = None):
        self.root = root
        self.path = path
        self.by_id: dict[str, etree._Element] = {}
        self.duplicate_ids: list[str] = []
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            i = el.get("id")
            if i:
                if i in self.by_id:
                    self.duplicate_ids.append(i)
                else:
                    self.by_id[i] = el

    # ---- loading ----------------------------------------------------------------------------
    @classmethod
    def parse(cls, source):
        parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
        if isinstance(source, (bytes, bytearray)):
            root = etree.fromstring(bytes(source), parser)
            return cls(root, None)
        tree = etree.parse(str(source), parser)
        return cls(tree.getroot(), str(source))

    # ---- lookups ----------------------------------------------------------------------------
    def get(self, ref):
        r = local_id(ref)
        return self.by_id.get(r) if r else None

    def of(self, *names):
        for el in self.root.iter():
            if isinstance(el.tag, str) and ns_of(el) == BPMN_NS and ln(el) in names:
                yield el

    def processes(self):
        return [c for c in kids(self.root, "process")]

    def collaborations(self):
        return [c for c in kids(self.root, "collaboration")]

    def choreographies(self):
        return [c for c in kids(self.root, "choreography")]

    def participants(self):
        for col in self.collaborations():
            for p in kids(col, "participant"):
                yield p

    def process_of_participant(self, part):
        return self.get(part.get("processRef")) if part.get("processRef") else None

    def container_of(self, el):
        """Nearest enclosing process / sub-process / choreography element."""
        p = el.getparent()
        while p is not None:
            if ln(p) in CONTAINERS and ns_of(p) == BPMN_NS:
                return p
            p = p.getparent()
        return None

    def flow_nodes(self, container):
        return [c for c in kids(container) if ln(c) in FLOW_NODES]

    def sequence_flows(self, container):
        return list(kids(container, "sequenceFlow"))

    def all_flow_nodes(self):
        return [e for e in self.of(*FLOW_NODES)]

    def participant_of(self, el):
        """The participant (pool) whose process (transitively) contains `el`, or None."""
        top = el
        p = el
        while p is not None:
            if ln(p) == "process" and ns_of(p) == BPMN_NS:
                top = p
                break
            p = p.getparent()
        if ln(top) != "process":
            return None
        for part in self.participants():
            if local_id(part.get("processRef")) == top.get("id"):
                return part
        return None

    # ---- event helpers ----------------------------------------------------------------------
    def event_triggers(self, ev) -> list[str]:
        out = []
        for c in kids(ev):
            n = ln(c)
            if n in EVENT_DEF_TAGS:
                out.append(EVENT_DEF_TAGS[n])
            elif n == "eventDefinitionRef":
                tgt = self.get(text_of(c))
                out.append(EVENT_DEF_TAGS.get(ln(tgt), "unknown") if tgt is not None else "unknown")
        return out

    def event_trigger(self, ev) -> str:
        t = self.event_triggers(ev)
        if not t:
            return "none"
        if len(t) > 1:
            return "parallelMultiple" if is_true(ev.get("parallelMultiple")) else "multiple"
        if is_true(ev.get("parallelMultiple")) and ln(ev) in ("startEvent", "intermediateCatchEvent", "boundaryEvent"):
            return "parallelMultiple"
        return t[0]

    def is_event_subprocess(self, el) -> bool:
        return ln(el) in SUBPROCS and is_true(el.get("triggeredByEvent"))

    def is_interrupting(self, ev) -> bool:
        if ln(ev) == "boundaryEvent":
            return is_true(ev.get("cancelActivity"), True)
        if ln(ev) == "startEvent":
            return is_true(ev.get("isInterrupting"), True)
        return True

    # ---- flow graph -------------------------------------------------------------------------
    def flows_from(self, node_id, container=None):
        res = []
        for sf in self.of("sequenceFlow"):
            if local_id(sf.get("sourceRef")) == node_id:
                res.append(sf)
        return res

    def flows_to(self, node_id):
        return [sf for sf in self.of("sequenceFlow") if local_id(sf.get("targetRef")) == node_id]

    def element_label(self, el) -> str:
        n = el.get("name")
        if n:
            return n
        if ln(el) == "textAnnotation":
            t = el.find(q("text"))
            return text_of(t)
        return ""

    # ---- bpmn:definitions -------------------------------------------------------------------
    def diagrams(self):
        return list(self.root.iterchildren(q("BPMNDiagram", BPMNDI_NS)))


def new_id(model: Model, prefix: str) -> str:
    i = 1
    while f"{prefix}_{i}" in model.by_id:
        i += 1
    nid = f"{prefix}_{i}"
    return nid


# ----------------------------------------------------------------------------------------------
# Conformance sub-classes (spec clause 2.2.2, Tables 2.1 - 2.4)
# ----------------------------------------------------------------------------------------------
def kind_of(model: Model, el) -> str | None:
    """A conformance 'kind' key for an element, e.g. 'startEvent:message',
    'boundaryEvent:timer:non-interrupting', 'sequenceFlow:conditional', 'userTask'.
    Returns None for elements that do not count towards a conformance sub-class
    (documentation, DI, definitions-level plumbing)."""
    n = ln(el)
    if n in EVENTS:
        trig = model.event_trigger(el)
        key = f"{n}:{trig}"
        if n == "boundaryEvent" and not model.is_interrupting(el):
            key += ":non-interrupting"
        if n == "startEvent" and not model.is_interrupting(el):
            key += ":non-interrupting"
        parent = model.container_of(el)
        if n == "startEvent" and parent is not None and model.is_event_subprocess(parent):
            key += ":in-event-subprocess"
        return key
    if n == "sequenceFlow":
        if el.find(q("conditionExpression")) is not None:
            return "sequenceFlow:conditional"
        src = model.get(el.get("sourceRef"))
        if src is not None and src.get("default") == el.get("id"):
            return "sequenceFlow:default"
        return "sequenceFlow"
    if n in ACTIVITIES:
        key = n
        if n == "subProcess" and model.is_event_subprocess(el):
            key = "eventSubProcess"
        lc = el.find(q("standardLoopCharacteristics"))
        mi = el.find(q("multiInstanceLoopCharacteristics"))
        if lc is not None:
            key += "+loop"
        if mi is not None:
            key += "+multiInstance"
        if is_true(el.get("isForCompensation")):
            key += "+compensation"
        return key
    if n in GATEWAYS or n in ARTIFACTS or n in ("association", "messageFlow", "participant", "lane",
                                                  "laneSet", "dataObject", "dataObjectReference",
                                                  "dataStoreReference", "dataStore", "dataInput",
                                                  "dataOutput", "message", "dataInputAssociation",
                                                  "dataOutputAssociation") or n in CONV_NODES \
            or n in CHOREO_ACTS or n in ("conversationLink", "correlationKey", "choreography",
                                         "globalChoreographyTask", "globalTask", "globalUserTask",
                                         "globalManualTask", "globalScriptTask",
                                         "globalBusinessRuleTask"):
        return n
    return None


# Event/flow kinds allowed per level, written exactly from Tables 2.1 and 2.2.
_D_EVENTS = {"startEvent:none", "endEvent:none"}
DESCRIPTIVE = {
    "participant", "laneSet", "lane", "sequenceFlow", "messageFlow", "exclusiveGateway",
    "parallelGateway", "task", "userTask", "serviceTask", "subProcess", "callActivity",
    "dataObject", "dataObjectReference", "dataStoreReference", "dataStore", "textAnnotation",
    "association", "dataInputAssociation", "dataOutputAssociation", "dataInput", "dataOutput",
    "message",  # DataInput/Output & Message are the supporting substructure
} | _D_EVENTS

_A_EXTRA = {
    "startEvent:message", "startEvent:timer", "startEvent:signal", "startEvent:conditional",
    "startEvent:message:non-interrupting", "startEvent:timer:non-interrupting",  # not in table; see note
    "endEvent:message", "endEvent:terminate", "endEvent:signal", "endEvent:error",
    "endEvent:escalation", "group", "sequenceFlow:conditional", "sequenceFlow:default",
    "sendTask", "receiveTask", "subProcess+loop", "subProcess+multiInstance", "task+loop",
    "task+multiInstance", "userTask+loop", "userTask+multiInstance", "serviceTask+loop",
    "serviceTask+multiInstance", "sendTask+loop", "sendTask+multiInstance", "receiveTask+loop",
    "receiveTask+multiInstance", "callActivity+loop", "callActivity+multiInstance",
    "inclusiveGateway", "eventBasedGateway",
    "intermediateCatchEvent:link", "intermediateThrowEvent:link",
    "intermediateCatchEvent:message", "intermediateThrowEvent:message",
    "boundaryEvent:message", "boundaryEvent:message:non-interrupting",
    "intermediateCatchEvent:timer", "boundaryEvent:timer", "boundaryEvent:timer:non-interrupting",
    "boundaryEvent:error", "boundaryEvent:escalation:non-interrupting",
    "intermediateThrowEvent:escalation",
    "intermediateCatchEvent:signal", "intermediateThrowEvent:signal", "boundaryEvent:signal",
    "boundaryEvent:signal:non-interrupting",
    "intermediateCatchEvent:conditional", "boundaryEvent:conditional",
    "boundaryEvent:conditional:non-interrupting",
}
# Table 2.2 does not list non-interrupting message/timer *start* events (only event sub-process use) -
# keep them out of Analytic to follow the table literally.
_A_EXTRA -= {"startEvent:message:non-interrupting", "startEvent:timer:non-interrupting"}
ANALYTIC = DESCRIPTIVE | _A_EXTRA

# Table 2.3 / 2.4 (Common Executable) - a different subset, not a superset of Analytic.
EXECUTABLE = {
    "sequenceFlow", "sequenceFlow:conditional", "sequenceFlow:default", "subProcess", "exclusiveGateway",
    "parallelGateway", "eventBasedGateway", "startEvent:none", "endEvent:none", "userTask",
    "serviceTask", "callActivity", "dataObject", "dataObjectReference", "textAnnotation",
    "dataInputAssociation", "dataOutputAssociation", "dataInput", "dataOutput", "message",
    "startEvent:message", "endEvent:message", "endEvent:terminate", "intermediateCatchEvent:message",
    "intermediateThrowEvent:message", "intermediateCatchEvent:timer", "boundaryEvent:error",
    "subProcess+loop", "subProcess+multiInstance", "userTask+loop", "userTask+multiInstance",
    "serviceTask+loop", "serviceTask+multiInstance", "callActivity+loop", "callActivity+multiInstance",
    "participant", "laneSet", "lane", "messageFlow", "association", "dataStoreReference", "dataStore",
}

LEVELS = {"descriptive": DESCRIPTIVE, "analytic": ANALYTIC, "executable": EXECUTABLE}
LEVEL_LABEL = {
    "descriptive": "Descriptive (Table 2.1)", "analytic": "Analytic (Tables 2.1+2.2)",
    "executable": "Common Executable subset (Tables 2.3+2.4)", "full": "Full Process Modeling Conformance",
}


def element_kinds(model: Model) -> dict[str, list[str]]:
    """kind -> [element ids] for every BPMN element that counts for conformance level."""
    out: dict[str, list[str]] = {}
    for el in model.root.iter():
        if not isinstance(el.tag, str) or ns_of(el) != BPMN_NS:
            continue
        # elements nested in ioSpecification etc. are plumbing; the kind function ignores them
        k = kind_of(model, el)
        if k:
            out.setdefault(k, []).append(el.get("id") or "(no id)")
    return out


def minimum_level(kinds) -> str:
    ks = set(kinds)
    if ks <= DESCRIPTIVE:
        return "descriptive"
    if ks <= ANALYTIC:
        return "analytic"
    return "full"


def slug(s: str, default="x") -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")
    return s or default
