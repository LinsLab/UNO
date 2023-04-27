# Copyright 2021 RLCard Team of Texas A&M University
# Copyright 2021 DouZero Team of Kwai
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import traceback

import numpy as np
import torch

shandle = logging.StreamHandler()
shandle.setFormatter(
    logging.Formatter(
        '[%(levelname)s:%(process)d %(module)s:%(lineno)d %(asctime)s] '
        '%(message)s'))
log = logging.getLogger('uno')
log.propagate = False
log.addHandler(shandle)
log.setLevel(logging.INFO)

def get_batch(free_queue,
              full_queue,
              buffers,
              batch_size,
              lock):
    with lock:
        indices = [full_queue.get() for _ in range(batch_size)] # 在 batch_size 大小的 buffers 中取 batch_size 大小的 batch 数据进行学习，达到抽样的效果
    batch = {
        key: torch.stack([buffers[key][m] for m in indices], dim=1)
        for key in buffers
    }
    for m in indices:
        free_queue.put(m)
    return batch

def create_buffers(T, num_buffers, state_shape, action_shape):
    buffers = []
    for device in range(torch.cuda.device_count()):
        buffers.append([])
        for player_id in range(len(state_shape)):
            specs = dict(
                done=dict(size=(T,), dtype=torch.bool),
                episode_return=dict(size=(T,), dtype=torch.float32),
                target=dict(size=(T,), dtype=torch.float32),
                obs_action=dict(size=(T,)+tuple(action_shape[player_id]), dtype=torch.int8),
                obs_x=dict(size=(T,)+tuple(state_shape[player_id]), dtype=torch.int8),
                obs_z=dict(size=(T, 4, 126), dtype=torch.int8),
            )
            _buffers: Buffers = {key: [] for key in specs}  # type: ignore
            for _ in range(num_buffers):
                for key in _buffers:
                    _buffer = torch.empty(**specs[key]).to(torch.device('cuda:'+str(device))).share_memory_()
                    _buffers[key].append(_buffer)
            buffers[device].append(_buffers)
    return buffers

def create_optimizers(num_players, learning_rate, momentum, epsilon, alpha, learner_model):
    optimizers = []
    for player_id in range(num_players):
        optimizer = torch.optim.RMSprop(
            learner_model.parameters(player_id),
            lr=learning_rate,
            momentum=momentum,
            eps=epsilon,
            alpha=alpha)
        optimizers.append(optimizer)
    return optimizers

def act(i, device, T, free_queue, full_queue, model, buffers, env):
    try:
        log.info('Device %i Actor %i started.', device, i)
        torch_device = torch.device('cuda:'+str(device))

        # Configure environment
        env.seed(i)
        env.set_agents(model.get_agents())

        done_buf = [[] for _ in range(env.num_players)]
        episode_return_buf = [[] for _ in range(env.num_players)]
        target_buf = [[] for _ in range(env.num_players)]
        obs_x_buf = [[] for _ in range(env.num_players)]
        obs_z_buf = [[] for _ in range(env.num_players)]
        obs_action_buf = [[] for _ in range(env.num_players)]
        size = [0 for _ in range(env.num_players)]

        while True:
            trajectories, payoffs = env.run(is_training=True)
            for p in range(env.num_players):
                size[p] += len(trajectories[p][:-1]) // 2
                diff = size[p] - len(target_buf[p])
                if diff > 0:
                    done_buf[p].extend([False for _ in range(diff-1)])
                    done_buf[p].append(True)
                    episode_return_buf[p].extend([0.0 for _ in range(diff-1)])
                    episode_return_buf[p].append(float(payoffs[p]))
                    target_buf[p].extend([float(payoffs[p]) for _ in range(diff)])
                    # State and action
                    for i in range(0, len(trajectories[p])-2, 2):
                        obs_x = trajectories[p][i]['x_batch'] # 获取本局游戏 玩家 p 的 state_x 部分
                        obs_z = trajectories[p][i]['z_batch'] # 获取本局游戏 玩家 p 的 state_z 部分
                        obs_action = env.get_action_feature(trajectories[p][i+1]) # 获取本局游戏 玩家 p 的所有 action（61 —— one-hot编码）
                        obs_x_buf[p].append(torch.from_numpy(obs_x))
                        obs_z_buf[p].append(torch.from_numpy(obs_z))
                        obs_action_buf[p].append(torch.from_numpy(obs_action))
                
                if size[p] > T: # 每个玩家 p 达到 T 次数据量时，将数据存入 queue 便于后续更新
                    index = free_queue[p].get()
                    if index is None:
                        break
                    for t in range(T):
                        buffers[p]['done'][index][t, ...] = done_buf[p][t]
                        buffers[p]['episode_return'][index][t, ...] = episode_return_buf[p][t]
                        buffers[p]['target'][index][t, ...] = target_buf[p][t]
                        buffers[p]['obs_x'][index][t, ...] = obs_x_buf[p][t]
                        buffers[p]['obs_z'][index][t, ...] = obs_z_buf[p][t]
                        buffers[p]['obs_action'][index][t, ...] = obs_action_buf[p][t]
                    full_queue[p].put(index)
                    done_buf[p] = done_buf[p][T:]
                    episode_return_buf[p] = episode_return_buf[p][T:]
                    target_buf[p] = target_buf[p][T:]
                    obs_x_buf[p] = obs_x_buf[p][T:]
                    obs_z_buf[p] = obs_z_buf[p][T:]
                    obs_action_buf[p] = obs_action_buf[p][T:]
                    size[p] -= T

    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error('Exception in worker process %i', i)
        traceback.print_exc()
        print()
        raise e
