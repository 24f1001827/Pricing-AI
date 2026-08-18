from langgraph.graph import StateGraph, START, END
from agents.state import AgentState 
from agents.nodes import *

def create_graph():
    graph = StateGraph(AgentState)

    graph.add_node("load_data", load_data)
    graph.add_node("eda", eda)
    graph.add_node("feature_engineering", feature_engineering)
    graph.add_node("train_model", train_model)
    graph.add_node("evaluate", evaluate)
    graph.add_node("critic_review", critic_review)
    graph.add_node("register_model", register_model)

    graph.set_entry_point("load_data")

    graph.add_edge("load_data", "eda")
    graph.add_edge("eda", "feature_engineering")
    graph.add_edge("feature_engineering", "train_model")
    graph.add_edge("train_model", "evaluate")
    graph.add_edge("register_model", END)

    graph.add_conditional_edges(
        "evaluate",
        lambda state: state["status"],
        {
            "train_model": "train_model",
            "critic_review": "critic_review",
            "failed": END
        }
    )

    graph.add_conditional_edges(
        "critic_review",
        lambda state: state["status"],
        {
            "register_model": "register_model",
            "eda": "eda",
            "feature_engineering": "feature_engineering",
            "train_model": "train_model"
        }
    )
    
    return graph.compile()

pipeline = create_graph()