# 📂 OFFICIAL RFP: OPERATION KINETIC RESPONSE

**MEMORANDUM FOR RECORD**

**FROM:** Department of Integrated Logistics (DIL) – Acquisition Board

**SUBJECT:** Solicitation for Autonomous Liaison Agent (ALA) Prototypes

**PROJECT:** Mini-Capstone "Redemption Week"

---

## I. THE MISSION OVERVIEW

The Department of Integrated Logistics (DIL) is currently facing an unprecedented **"Action Gap."** Our legacy systems are overwhelmed by unstructured data, leading to critical delays in decision-making. We are seeking a unified **Autonomous Liaison Agent (ALA)** capable of independent reasoning and cross-functional execution.

Your firm has **one week** to develop a functional MVP (Minimum Viable Product) to prove that your architecture can handle high-stakes operational environments using **AWS Bedrock**.

---

## II. CORE TECHNICAL REQUIREMENT: AGENTIC WORKFLOWS

To qualify for the contract, your solution must move beyond simple chatbots. The DIL requires a **Multi-Agent System** where at least **three specialized agents** collaborate to complete a single task.

Constraints:

- **Specialization:** Each of the three agents must have a distinct "System Prompt" and a unique responsibility within the project.
- **Orchestration:** You must demonstrate a clear handoff or communication bridge between agents. (e.g., Agent 1’s output triggers Agent 2, or Agent 3 audits the work of Agent 1).
- **Functional Autonomy:** At least one agent must be capable of autonomously using a Tool/Action (Lambda, API, or DB) based on the reasoning provided by the other agents.

---

## III. THE THREE OPERATIONAL TRACKS (FIELD REPORTS)

Each firm must choose one of the following "High-Friction" areas. The DIL does not have a solution. Your firm must propose a **three-agent architecture** that solves the specific pain point described.

### Track 1: The "Chaos" Sector (Public Safety & Crisis)

**The Field Report:** _"During recent emergencies in the Borderplex, we've seen a total breakdown in information flow. We have raw data coming from 911 dispatch, weather sensors, and social media, but by the time a human reads it, the situation has changed. We are losing the 'Golden Hour' of response."_

**The Challenge:** How can your three agents turn this "Information Overload" into a tangible, real-world action?

### Track 2: The "Entropy" Sector (Infrastructure & Systems)

**The Field Report:** _"Our DevOps teams are burnt out. We have high-availability systems that are throwing thousands of logs an hour. Most are noise, but somewhere in there is the signal of a coming crash. We can't hire enough engineers to monitor the logs and execute the necessary system adjustments manually."_

**The Challenge:** How will your agents proactively identify and neutralize infrastructure threats before they escalate?

### Track 3: The "Labyrinth" Sector (Governance & Citizen Service)

**The Field Report:** _"The DIL is currently facing a backlog of thousands of citizen applications and regulatory inquiries. The rules are buried in 500-page manuals. When people call for updates, our clerks can't find their files. We are failing the public because our 'Knowledge' is locked in static PDFs."_

**The Challenge:** How can your agents bridge the gap between Complex Regulations and Final User Outcomes?

---

## IV. DATA OPERATIONAL STANDARDS

Your firm is responsible for sourcing the data to "train" and test your agents. To meet DIL standards, your **Validation Set** must include:

| Requirement              | Specification                                                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| **Volume**               | Minimum of 5 distinct documents (PDF, TXT, or Markdown)                                                                         |
| **Complexity**           | At least one document must be "Dense" (5+ pages of technical, regulatory, or messy log data)                                    |
| **Signal-to-Noise Test** | Data should be raw and uncleaned — agents must prove they can ignore headers, footers, and legal jargon to find actionable info |
| **Conflict Scenario**    | At least two documents with slightly conflicting or outdated info to demonstrate ambiguity handling                             |

---

## V. FIRM REQUIREMENTS (THE "PICK THREE")

In addition to the Multi-Agent Bedrock requirement, your firm must choose and successfully integrate **three** additional concepts from the AI DevOps curriculum:

- [ ] **Automated CI/CD** — Fully automated deployment (e.g., GitHub Actions with automations)
- [ ] **Infrastructure as Code (IaC)** — Environment managed via Terraform or CDK
- [ ] **Observability** — Live logging/dashboards for agent performance and cost
- [ ] **Vector Integration** — RAG implementation using Knowledge Bases for Bedrock
- [ ] **Security & Governance** — Implementation of Bedrock Guardrails and IAM least-privilege
- [ ] **Hybrid ML Infrastructure (SageMaker + K8s)**: Deploy and manage a specialized ML model endpoint using SageMaker Operators for Kubernetes. Your agents must call this endpoint to perform a domain-specific calculation or prediction.

---

## VI. INTERFACE EXPECTATIONS

The DIL will **not** accept raw code. Every prototype must include a **Graphical User Interface (GUI)**.

- **Web-based GUI:** Must be clean, functional, and show "Thinking/Action" states.
- **Terminal UI (TUI):** Must use libraries like `Rich` or `Inquirer` to provide a professional, structured "Command Center" experience (including statuses).

---

## VII. DATA SOURCES "HINT" SHEET

If your firm is struggling to source high-fidelity data, consider searching for:

**Government/Municipal:**

- City Council meeting minutes
- Municipal codes
- VA benefit handbooks

**Technical/DevOps:**

- AWS CloudWatch log samples
- PagerDuty post-mortems
- Open-source repo READMEs

**Emergency:**

- FEMA Incident Action Plans
- TDEM public situational reports
- National Weather Service bulletins

---

## VIII. THE PITCH TIMELINE

Your Instructor / Cirriculum will specify the time you have to brainstorm with your pre-assigned group. You will then present a **2-minute elevator pitch** to the Lead Instructor for "Contract Approval."

> ⚠️ **BE WARNED:** The DIL reserves the right to issue **"Market Volatility Alerts" (Wrenches)** throughout the week. Your architecture must be flexible enough to pivot on command.

## IX. THE COMPANY

Your company (group) is pre-selected (to. mimic the real world), you can find your company coworkers [here](groups.md).

You will be required to have a 15-minute standup with your coworkers at the start of each class to ensure your group is up-to-date on the project;s current progress, and the objective for the day.

Each company will work with one forked repo, each coworker must have their own commits for there companies repo.
