''' An example of training a Deep Monte-Carlo (DMC) Agent on the environments in RLCard
'''
import os
import argparse

import torch

import rlcard
from rlcard.agents.dmc_agent import DMCTrainer

def train(args):

    # Make the environment
    env = rlcard.make(args.env)

    # Initialize the DMC trainer
    trainer = DMCTrainer(env,
                         load_model=args.load_model,
                         savedir=args.savedir,
                         total_frames=args.total_frames,
                         num_eval_games=args.num_eval_games,
                         save_interval=args.save_interval,
                         num_actor_devices=args.num_actor_devices,
                         num_actors=args.num_actors,
                         training_device=args.training_device)

    # Train DMC Agents
    trainer.start()

if __name__ == '__main__':
    parser = argparse.ArgumentParser("DMC example in RLCard")
    parser.add_argument('--env', type=str, default='uno',
            choices=['blackjack', 'doudizhu', 'uno'])
    parser.add_argument('--cuda', type=str, default='1')
    parser.add_argument('--load_model', action='store_true',
                    help='Load an existing model')
    parser.add_argument('--savedir', default='experiments/uno/dmc',
                        help='Root dir where experiment data will be saved')
    parser.add_argument('--total_frames', default=10000000000, type=int)
    parser.add_argument('--num_eval_games', default=10000, type=int)
    parser.add_argument('--save_interval', default=30, type=int,
                        help='Time interval (in minutes) at which to save the model')
    parser.add_argument('--num_actor_devices', default=1, type=int,
                        help='The number of devices used for simulation')
    parser.add_argument('--num_actors', default=1, type=int,
                        help='The number of actors for each simulation device')
    parser.add_argument('--training_device', default=0, type=int,
                        help='The index of the GPU used for training models')

    args = parser.parse_args()

    os.environ["CUDA_VISIBLE_DEVICES"] = args.cuda
    train(args)