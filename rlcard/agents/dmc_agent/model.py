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

import numpy as np

import torch
from torch import nn

class DMCNet(nn.Module):
    def __init__(self,
                 state_shape,
                 action_shape,
                 mlp_layers=[512,512,512,512,512]):
        super().__init__()
        self.lstm = nn.LSTM(126, 128, batch_first=True)
        input_dim = np.prod(state_shape) + 128 + np.prod(action_shape) # 将不同 Agent 状态空间与动作空间大小相加
        layer_dims = [input_dim] + mlp_layers
        fc = []
        for i in range(len(layer_dims)-1):
            fc.append(nn.Linear(layer_dims[i], layer_dims[i+1]))
            fc.append(nn.ReLU())
        fc.append(nn.Linear(layer_dims[-1], 1)) # 网络层最后输出为 1
        self.fc_layers = nn.Sequential(*fc)

    def forward(self, x, z, actions):
        lstm_out, (h_n, _) = self.lstm(z)
        lstm_out = lstm_out[:, -1, :]
        obs = torch.cat([x, lstm_out], dim=-1)
        obs = torch.flatten(obs, 1)
        actions = torch.flatten(actions, 1)
        x = torch.cat((obs, actions), dim=1)
        values = self.fc_layers(x).flatten()
        return values

class DMCAgent:
    def __init__(self,
                 state_shape,
                 action_shape,
                 mlp_layers=[512,512,512,512,512],
                 exp_epsilon=0.01,
                 device=0):
        self.use_raw = False
        self.device = torch.device('cuda:'+str(device))
        self.net = DMCNet(state_shape, action_shape, mlp_layers).to(self.device)
        self.exp_epsilon = exp_epsilon
        self.action_shape = action_shape

    def step(self, state):
        action_keys, values = self.predict(state)

        if self.exp_epsilon > 0 and np.random.rand() < self.exp_epsilon: # 以 𝛆 的概率探索
            action = np.random.choice(action_keys)
        else: # 以 1 - 𝛆 的概率利用
            action_idx = np.argmax(values)
            action = action_keys[action_idx]

        return action

    def eval_step(self, state):
        action_keys, values = self.predict(state)

        action_idx = np.argmax(values)
        action = action_keys[action_idx]

        info = {}
        info['values'] = {state['raw_legal_actions'][i]: float(values[i]) for i in range(len(action_keys))}

        return action, info

    def share_memory(self):
        self.net.share_memory()

    def eval(self):
        self.net.eval()

    def parameters(self):
        return self.net.parameters()

    def predict(self, state):
        # Prepare obs and actions
        x_batch = state['x_batch'].astype(np.float32)
        z_batch = state['z_batch'].astype(np.float32)
        legal_actions = state['legal_actions']
        action_keys = np.array(list(legal_actions.keys()))
        action_values = list(legal_actions.values())
        # One-hot encoding if there is no action features —— 给 action_values 按照 action 下标进行 one-hot 编码
        for i in range(len(action_values)):
            if action_values[i] is None:
                action_values[i] = np.zeros(self.action_shape[0])
                action_values[i][action_keys[i]-1] = 1
        action_values = np.array(action_values, dtype=np.float32) # 统一 action_values 的数据格式

        x_batch = np.repeat(x_batch[np.newaxis, :], len(action_keys), axis=0) # 统一 x_batch 的数据格式
        z_batch = np.repeat(z_batch[np.newaxis, :, :], len(action_keys), axis=0)# 统一 z_batch 的数据格式

        # Predict Q values
        values = self.net.forward(torch.from_numpy(x_batch).to(self.device),
                                  torch.from_numpy(z_batch).to(self.device),
                                  torch.from_numpy(action_values).to(self.device))

        return action_keys, values.cpu().detach().numpy()

    def forward(self, x, z, actions):
        return self.net.forward(x, z, actions)

    def load_state_dict(self, state_dict):
        return self.net.load_state_dict(state_dict)

    def state_dict(self):
        return self.net.state_dict()

    def set_device(self, device):
        self.device = device

class DMCModel:
    def __init__(self,
                 state_shape,
                 action_shape,
                 mlp_layers=[512,512,512,512,512],
                 exp_epsilon=0.01,
                 device=0):
        self.agents = []
        for player_id in range(len(state_shape)):
            agent = DMCAgent(state_shape[player_id],
                             action_shape[player_id],
                             mlp_layers,
                             exp_epsilon,
                             device)
            self.agents.append(agent)

    def share_memory(self):
        for agent in self.agents:
            agent.share_memory()

    def eval(self):
        for agent in self.agents:
            agent.eval()

    def parameters(self, index):
        return self.agents[index].parameters()

    def get_agent(self, index):
        return self.agents[index]

    def get_agents(self):
        return self.agents
