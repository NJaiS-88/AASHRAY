import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axiosClient from '../api/axiosClient';
import useAuthStore from '../store/useAuthStore';

function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const setUser = useAuthStore((state) => state.setUser);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const { data } = await axiosClient.post('/auth/signup', { name, email, password });
      setUser(data);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.message || 'Signup failed');
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-white text-black">
      <form onSubmit={handleSubmit} className="flex flex-col w-64 space-y-4">
        {error && <div className="text-red-500 text-sm">{error}</div>}
        <input 
          type="text" 
          placeholder="name" 
          className="border border-gray-300 p-2" 
          value={name} 
          onChange={(e) => setName(e.target.value)} 
          required 
        />
        <input 
          type="email" 
          placeholder="email" 
          className="border border-gray-300 p-2" 
          value={email} 
          onChange={(e) => setEmail(e.target.value)} 
          required 
        />
        <input 
          type="password" 
          placeholder="password" 
          className="border border-gray-300 p-2" 
          value={password} 
          onChange={(e) => setPassword(e.target.value)} 
          required 
        />
        <button type="submit" className="bg-black text-white p-2">signup</button>
        <Link to="/login" className="text-sm text-center text-gray-500 hover:text-black">login instead</Link>
      </form>
    </div>
  );
}

export default Signup;
