# Official BPMN 2.0 schemas (OMG machine-consumable files)

`BPMN20.xsd`, `Semantic.xsd`, `BPMNDI.xsd`, `DC.xsd`, `DI.xsd` are the OMG BPMN 2.0 XSDs named on the
title page of the specification (formal/2013-12-09, v2.0.2: "Machine consumable files"). They are
unchanged since BPMN 2.0 (namespace `http://www.omg.org/spec/BPMN/20100524/MODEL`).

Provenance: copied from the Camunda `camunda-bpmn-model` repository's mirror of the OMG files because
omg.org is not reachable from the build sandbox. They were cross-checked against the schema fragments
printed in the spec (every complexType/element name in the spec appears here) and they compile with lxml.
To refresh from the source of truth, download the five files from
`http://www.omg.org/spec/BPMN/20100501/` (BPMN20.xsd, Semantic.xsd, BPMNDI.xsd, DC.xsd, DI.xsd) and overwrite.
