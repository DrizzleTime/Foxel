import React, { createContext, useContext, useState, useEffect } from 'react';
import { authApi, type MeResponse } from '../api/auth';

interface AuthContextType {
    token: string | null;
    isAuthenticated: boolean;
    login: (username: string, password: string) => Promise<void>;
    logout: () => void;
    register: (username: string, password: string, email?: string, full_name?: string) => Promise<void>;
    user: MeResponse | null;
    refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({} as any);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [token, setToken] = useState<string | null>(() => localStorage.getItem('token'));
    const [user, setUser] = useState<MeResponse | null>(null);
    const isAuthenticated = !!token;

    useEffect(() => {
        if (token) localStorage.setItem('token', token);
        else localStorage.removeItem('token');
    }, [token]);

    const login = async (username: string, password: string) => {
        const res = await authApi.login({ username, password });
        if (res) {
            setToken(res.access_token);
            try { await refreshUser(); } catch { void 0; }
        }
    };

    const logout = () => {
        setToken(null);
        setUser(null);
    };

    const register = async (username: string, password: string, email?: string, full_name?: string) => {
        await authApi.register(username, password, email, full_name);
    };

    const refreshUser = async () => {
        if (!localStorage.getItem('token')) { setUser(null); return; }
        const me = await authApi.me();
        setUser(me);
    };

    useEffect(() => {
        if (token) {
            refreshUser().catch(() => setUser(null));
        } else {
            setUser(null);
        }
    }, [token]);

    return (
        <AuthContext.Provider value={{ token, isAuthenticated, login, logout, register, user, refreshUser }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}
