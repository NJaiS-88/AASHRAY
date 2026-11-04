import axios from 'axios';

const axiosClient = axios.create({
    baseURL: import.meta.env.VITE_API_URL || 'http://localhost:5000/api',
    withCredentials: true,
});

axiosClient.interceptors.request.use((config) => {
    try {
        const stored = localStorage.getItem('user');
        if (stored) {
            const user = JSON.parse(stored);
            if (user?.token) {
                config.headers.Authorization = `Bearer ${user.token}`;
            }
        }
    } catch (e) {
        // ignore parse error
    }
    return config;
});

export default axiosClient;
