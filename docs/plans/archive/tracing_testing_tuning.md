Here's what I expect from my node evaluation tool:
When we run our agent, every node is traced and saved locally as a log until we turn off that config parameter
the log includes the state upon entry, any fully compiled prompts sent to LLM, the LLM response, the state upon exit.
I want a tool I can call from any command line 'anode'. Parameter 1 = node name (or full) parameter 2 -N where N is the number of logs you want analyzed in a single pull.

The tool will pull the node traces for the last N runs, isolate the node being studied, then run the output through a carefully crafted LLM prompt that will identify if the node is performing as expected. The prompt should look at what is passed in, is it useful? How was the prompt constructed, does the context make sense? Do we have access to information in the state that we're not using? is there information we should try to develop to improve prompt accuracy and performance? should we adjust temperature settings? are we using the right model for the LLM calls (if any) . trace sould also include the cost of each LLM call and the total run at the top of the trace. 

The anode tool will use the name of the node passed to go to the nodes folder and find the file, the source code will be included as context for analysis. Make sure API keys aren't exposed in the prompts we send. 

The prompt needs to be different for the whole graph (full) runs, it needs to look at the README.MD in the project root, then look at the graph structure, and how all the nodes work, then maybe write a couple different reports it stitches together. 

We also need a script where we can automate runs of the agent to generate nodes for analysis. I should be able to add scripts just by passing in lists of strings in the order I want them sent. at the end of the list it should END the conversation. I want a folder of conversation files and I want to be able to run that from command line as well with 'agentscript' argument1 = the script argument2 = stream conversation argument3 = level of verbosity in debugging. The run should be formatted beautifully for ease of reading and the user should be able to pause the run at the next interrupt by hitting enter, then resume by hitting enter.

Can you isolate both of these scripts and create a README file so that I can import them as a toolkit for analysis in other LLM projects? I want the rolls royce of agent performance tuning tools that I can bring to any langgraph project and implement with a few AGENTS.MD instructions and an import. 

Maybe there are other scripts we can run to test for common pitfalls, like not building a graph and manually orchestrating. I'm inexperienced here so I need your imagination. 
