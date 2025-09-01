#!/usr/bin/env python3
"""
SSH Encryption Diagnostic Tool
Tests different SSH encryption methods and their performance
"""

import subprocess
import time
import sys

def test_ssh_cipher(cipher, remote_user, remote_ip, password, test_count=3):
    """Test a specific SSH cipher and return average latency"""
    print(f"🔐 Testing cipher: {cipher}")
    
    latencies = []
    for i in range(test_count):
        cmd = f"sshpass -p '{password}' ssh -c {cipher} -o StrictHostKeyChecking=no -o ConnectTimeout=10 {remote_user}@{remote_ip} 'echo \"Test {i+1}\"'"
        
        start_time = time.time()
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        end_time = time.time()
        
        if result.returncode == 0:
            latency = (end_time - start_time) * 1000  # Convert to ms
            latencies.append(latency)
            print(f"   Test {i+1}: {latency:.1f} ms")
        else:
            print(f"   Test {i+1}: Failed")
    
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        return avg_latency, min_latency, max_latency
    else:
        return None, None, None

def test_ssh_connection_quality(remote_user, remote_ip, password):
    """Test basic SSH connection quality"""
    print("🔍 Testing SSH connection quality...")
    
    # Test basic connectivity
    print("\n📡 Basic connectivity test...")
    basic_cmd = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {remote_user}@{remote_ip} 'echo \"Connection test successful\"'"
    
    start_time = time.time()
    result = subprocess.run(basic_cmd, shell=True, capture_output=True, text=True, timeout=15)
    end_time = time.time()
    
    if result.returncode == 0:
        latency = (end_time - start_time) * 1000
        print(f"✅ Basic SSH connection: {latency:.1f} ms")
        return latency
    else:
        print("❌ Basic SSH connection failed")
        return None

def test_ssh_ciphers(remote_user, remote_ip, password):
    """Test different SSH ciphers for performance"""
    print("\n🔐 Testing SSH cipher performance...")
    
    # Modern ciphers (faster, more secure)
    modern_ciphers = [
        "aes128-gcm@openssh.com",    # Fastest, most secure
        "aes256-gcm@openssh.com",    # Very fast, very secure
        "aes128-ctr",                # Fast, secure
        "aes256-ctr",                # Fast, very secure
        "chacha20-poly1305@openssh.com"  # Fast on ARM, secure
    ]
    
    # Legacy ciphers (slower, less secure)
    legacy_ciphers = [
        "aes128-cbc",                # Slower, less secure
        "aes256-cbc",                # Slower, less secure
        "3des-cbc"                   # Very slow, deprecated
    ]
    
    print("\n🚀 Testing modern ciphers (recommended):")
    modern_results = {}
    
    for cipher in modern_ciphers:
        avg_latency, min_latency, max_latency = test_ssh_cipher(cipher, remote_user, remote_ip, password)
        if avg_latency is not None:
            modern_results[cipher] = {
                'avg': avg_latency,
                'min': min_latency,
                'max': max_latency
            }
            print(f"   {cipher}: Avg {avg_latency:.1f}ms (Min: {min_latency:.1f}ms, Max: {max_latency:.1f}ms)")
        else:
            print(f"   {cipher}: Failed")
    
    print("\n🐌 Testing legacy ciphers (for comparison):")
    legacy_results = {}
    
    for cipher in legacy_ciphers:
        avg_latency, min_latency, max_latency = test_ssh_cipher(cipher, remote_user, remote_ip, password)
        if avg_latency is not None:
            legacy_results[cipher] = {
                'avg': avg_latency,
                'min': min_latency,
                'max': max_latency
            }
            print(f"   {cipher}: Avg {avg_latency:.1f}ms (Min: {min_latency:.1f}ms, Max: {max_latency:.1f}ms)")
        else:
            print(f"   {cipher}: Failed")
    
    return modern_results, legacy_results

def analyze_results(modern_results, legacy_results):
    """Analyze and recommend the best cipher"""
    print("\n📊 Analysis and Recommendations:")
    
    if not modern_results:
        print("❌ No modern ciphers worked. Check SSH connection.")
        return
    
    # Find fastest modern cipher
    fastest_modern = min(modern_results.items(), key=lambda x: x[1]['avg'])
    print(f"🏆 Fastest modern cipher: {fastest_modern[0]} ({fastest_modern[1]['avg']:.1f}ms)")
    
    # Compare with legacy if available
    if legacy_results:
        fastest_legacy = min(legacy_results.items(), key=lambda x: x[1]['avg'])
        print(f"🐌 Fastest legacy cipher: {fastest_legacy[0]} ({fastest_legacy[1]['avg']:.1f}ms)")
        
        speedup = fastest_legacy[1]['avg'] / fastest_modern[1]['avg']
        if speedup > 1.2:
            print(f"💡 Modern cipher is {speedup:.1f}x faster than legacy")
    
    # Performance categories
    print("\n📈 Performance Categories:")
    for cipher, data in modern_results.items():
        if data['avg'] < 50:
            performance = "🚀 Excellent"
        elif data['avg'] < 100:
            performance = "✅ Good"
        elif data['avg'] < 200:
            performance = "⚠️  Fair"
        else:
            performance = "❌ Poor"
        
        print(f"   {cipher}: {performance} ({data['avg']:.1f}ms)")
    
    # Recommendations
    print("\n💡 Recommendations:")
    print("1. Use the fastest modern cipher for best performance")
    print("2. Avoid legacy ciphers (slower and less secure)")
    print("3. If all ciphers are slow, check network quality")
    print("4. Consider using the fastest cipher in your SSH config")

def main():
    print("=" * 60)
    print("🔐 SSH Encryption Diagnostic Tool")
    print("=" * 60)
    
    # Get connection details
    print("\n📋 Enter connection details:")
    remote_user = input("SSH Username: ").strip()
    remote_ip = input("Remote IP: ").strip()
    password = input("SSH Password: ").strip()
    
    if not all([remote_user, remote_ip, password]):
        print("❌ All fields are required!")
        return
    
    print(f"\n🔍 Testing SSH connection to {remote_user}@{remote_ip}...")
    
    # Test basic connection first
    basic_latency = test_ssh_connection_quality(remote_user, remote_ip, password)
    if basic_latency is None:
        print("❌ Cannot establish SSH connection. Check credentials and network.")
        return
    
    # Test different ciphers
    modern_results, legacy_results = test_ssh_ciphers(remote_user, remote_ip, password)
    
    # Analyze results
    analyze_results(modern_results, legacy_results)
    
    print("\n✅ SSH encryption diagnostic completed!")

if __name__ == "__main__":
    main()

