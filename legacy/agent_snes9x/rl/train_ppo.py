import os
import time
import logging
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback
from agent.rl.lufia_env import Lufia2Env

def train_agent():
    """
    Initializes and trains the PPO reinforcement learning agent for navigation and combat.
    """
    logging.basicConfig(level=logging.INFO)
    logging.info("Initializing Lufia 2 RL Environment...")
    
    # Needs to be matched with your emulator window/hook
    env = Lufia2Env(render_mode="ansi")
    
    model_dir = "models/ppo_lufia2"
    os.makedirs(model_dir, exist_ok=True)
    
    # Save a checkpoint every 10,000 steps
    checkpoint_callback = CheckpointCallback(
        save_freq=10000,
        save_path=model_dir,
        name_prefix="rl_model"
    )

    logging.info("Creating PPO Model...")
    # PPO hyperparams are relatively standard for generic tasks.
    # We use a Multi-Layer Perceptron (MlpPolicy) since our observation space is a 1D vector (X, Y, HP, etc.)
    model = PPO(
        "MlpPolicy", 
        env, 
        verbose=1, 
        tensorboard_log="./ppo_lufia2_tensorboard/",
        learning_rate=0.0003,
        n_steps=2048,
        batch_size=64
    )
    
    logging.info("Starting Training Loop. (Make sure Emulator is running and C# Helper is attached!)")
    
    try:
        # Train for 500,000 timesteps initially
        model.learn(total_timesteps=500000, callback=checkpoint_callback)
        model.save(f"{model_dir}/final_model")
        logging.info("Training complete and model saved.")
    except KeyboardInterrupt:
        logging.info("Training interrupted manually. Saving current model state...")
        model.save(f"{model_dir}/interrupted_model")
    finally:
        env.close()

if __name__ == "__main__":
    train_agent()
