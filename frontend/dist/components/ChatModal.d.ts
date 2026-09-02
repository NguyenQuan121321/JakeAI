import React from 'react';
import { JakeProps } from '../types';
import { AIService } from '../services/aiService';
interface ChatModalProps extends JakeProps {
    isOpen: boolean;
    onClose: () => void;
    aiService: AIService;
    corgiPos?: {
        x: number;
        y: number;
    };
}
export declare const ChatModal: React.FC<ChatModalProps>;
export {};
