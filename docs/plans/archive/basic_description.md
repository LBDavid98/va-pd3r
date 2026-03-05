

## Nodes - NOTE: My notes are illustrative, not exhaustive. Enrich pleaseTA

Init -> User_Input -> Intent -> Router [QuestionSubGraph | UpdateInformation | DraftSubgraph | Unrecognized | END | INIT ] -> Combine_Responses -> PrepareNextStep -> User_Input


### init - initializes the base state and identifies what environment its running under
IN: AgentState
OUT: AgentState, AI_Message (Greet user, introduce self. Offer to help write a position description)
DESTINATION_IF_CONFIRMED: START_POSITIONCaCCCCC
- Inherits some basic awareness like organizational alignment (VHA, Digital Health Office, {SubOffice})

### User_input - interrupt for user input. input may be a message, a message and a file. 
IN: AgentState, previous user input if returning from interrupt
OUT: UserMessage, AgentState

### Intent_Classification (LLM)
POSSIBLE_INTENTS: ASK_QUESTION, PROVIDE_INFORMATION, CONFIRM, REJECT, MODIFY_ANSWER
IN: DESTINATION_IF_CONFIRMED, DESTINATION_IF_REJECTED
HARD RULE: WE DO NOT USE HEURISTICS FOR ANYTHING BUT: quit, restart, current_state

Output Example
---
Intents Identified: Ask Question, Provide information.
Intent1: ask_question
- Question: {question}
- HR_Specific: TRUE/FALSE
- PD3r_Process_Question: TRUE/FALSE
Intent2: provide_information (repeatable)
- field_answered: {position_title (example)}
- answer_provided: {The position title is Janitor and}
- field_type: str
Intent3: provide_information (repeatable)
- field_answered: {organizational structure}
- answer_provided: {he works for the Environmental Management Service under the digital health office}
- answer_mapping: {'organization': ['Veterans Health Administration', 'Digital Health Office', 'Environmental Management Service']}
- field_type: list(str)

Use Jinja Based on current phase in the state, change context based on current step. 

### ASK_QUESTION
RAG lookup if within topic of HR (vector store)
EDGES: LOOKUP, NOT_IN_SCOPE

### LOOKUP
Vector / semantic search for well cited information (page #, exact quote ideally intact i.e. entire section)

### MAP_ANSWER
Destination for provide_information and modify_answer

### SYNTHESIZE_NODE_RESPONSES
Combine the node responses from parallel nodes into an AI_Message

### CONSTRUCT_ANSWER (LLM)


## Ideal user experience

Agent: Hi, I'm PD3r, you can call me Pete. I help write Federal Position descriptions. Would you like me to help you write a PD?

User: Sure, that sounds good.

Pete: Great, in order to write a PD I need the following information from you:
 - Position Title - What is the name of the position as it appears on the org chart?
 - Organization - Where does this position fall in the organization, include higher offices.
 - ...
 - Is the position supervisory? 
 - (conditional:supverisory yes) number of people supervised
 - ...
 - (conditional:supverisory yes) percent of time spent supervising

 Up Next: Please provide the position title.

User: I'm hiring an IT integrations pecialist who will work under the Chief AI Officer

Pete: Great, I've mapped your answers for title and reports to. 
 - Mapped Answers: {answer1\nanswer2\n}
 - Still Needed: {missing_fields}
 Next, I need to know is the position supervisory?

 User: Why Does that Matter:

Pete: Supervisory positions require additional factors for evaluation. YOu can learn more about that here. (link to RAG source material in vector store)

Next up: I still need to know if the position is supervisory.

... Interview continues

Pete: That wraps it up, here are your answers:
 {answers}
 Does everything look ok?

User: ACtually, can we change the title to XYZ?

Pete: Sure, I've updated the answers.
 {answers}
 Does everything look ok?

User: Yes

Pete:  Great, we're ready to start writing. A position description consists of the following elements:
Introduction, Background, Major Duties (each builds off of each other and your responses)
Factor Levels (written all at once then reviewed)
Supervisory Factors if Applicable

Let's get started with the introduction:

{writing -> QA node -> next_step(feedback) | rewrite -> QA Node -> next_step(feedback)

Pete: Here you go:
{draft element}
Do you approve or need revisions?

User: Feedback

Pete: Thanks, I'll work that into the draft.

{writing subgraph}

Pete: Here's an updated draft incorporating your feedback:
{draft element}

User: THat's good

Pete: Here's the next draft element:

{iterate through all draft elements until all are approved)

Pete: Great job, we've completed our position description. Here's the final draft for your approval.

User: can you update factor3 so that it emphasizes the need for {random thing user is asking for}

Pete: Of course, just a minute. {Have 3-5 randomr responses like this for each helpful I'm about to do something moment}

{writing}

Pete: Here you go, I hope this meets your needs:

User: That's perfect thank you

Pete: Would you like to write another PD?

User: I hope I don't have to do another for a while.

Pete: Thanks for working with me! have a nice day. 

END


...

Agent: 

## Design ideas
 (note: need to be able to fill out a template for required interview fields, template should provide
 the langauge for the next_step prompt, instructions for the LLM to assist in mapping, etc.
